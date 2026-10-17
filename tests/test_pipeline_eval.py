import pytest

from filing_assistant.answer import REFUSAL
from filing_assistant.evaluate import (
    eval_answers,
    eval_refusal,
    eval_retrieval,
    is_numeric_question,
    numeric_match,
    parse_number,
    recall_at_k,
    unanswerable_variant,
)
from filing_assistant.financebench import Question
from filing_assistant.pipeline import Assistant, AssistantConfig
from filing_assistant.rerank import get_reranker
from filing_assistant.retrieve import Retriever
from tests.conftest import FakeClient, make_hit, tool_call

ex = pytest.mark.exercise
Q = "What was Northwind's FY2023 capital expenditure in USD millions?"


def test_parse_number():
    assert parse_number("$1577.00") == (1577.0, False, False)
    assert parse_number("(1,577) — Purchases") == (1577.0, False, False)
    assert parse_number("$8.7 billion in FY2022") == (8.7e9, False, True)
    assert parse_number("In FY2018 margin was 24.8%")[:2] == (24.8, True)
    assert parse_number("no numbers") is None


@ex
@pytest.mark.parametrize(("pred", "gold", "ok"), [
    ("(1,577) — Purchases of PP&E (FY2018) [1]", "$1577.00", True),
    ("USD 1,577 million", "$1577.00", True),
    ("$1.577 billion", "$1577.00", True),
    ("1,600", "$1577.00", False),
    ("24.8%", "24.8%", True),
    ("I can't answer that", "$10", False),
    ("$8.7 billion", "$8.7 million", False),
])
def test_numeric_match(pred, gold, ok):
    assert numeric_match(pred, gold) is ok


@ex
def test_recall_at_k():
    hits = [make_hit("a", doc="D", page=2), make_hit("b", doc="D", page=7),
            make_hit("c", doc="E", page=7)]
    assert recall_at_k(hits, "D", [7], 2) and not recall_at_k(hits, "D", [7], 1)
    assert not recall_at_k(hits, "E", [1], 3)
    assert recall_at_k(hits, "E", [], 3)


def test_question_helpers():
    q = Question("1", "3M", "3M_2018_10K", "3M capex in FY2018 and 2017?", "$1577", "m", None)
    assert unanswerable_variant(q) == "3M capex in FY1999 and 1999?"
    assert unanswerable_variant(Question("2", "x", "d", "no year", "", "m", None)) is None
    assert is_numeric_question(q)
    assert not is_numeric_question(Question("3", "x", "d", "q", "Yes, margins rose because...",
                                            "d", None))


@ex
def test_extractive_assistant_on_demo(demo_index, demo_questions):
    a = Assistant(demo_index, AssistantConfig(answer_mode="extractive", embedder="lsa"))
    ans = a.ask(Q)
    assert ans.answer.startswith("(285)") and not ans.refused and ans.mode == "extractive"
    assert ans.citations[0]["page"] == 5 and ans.cost_usd is None
    assert set(ans.timings_ms) == {"retrieve", "rerank", "generate", "total"}
    refused = a.ask("What was Northwind's capital expenditure in FY1999?")
    assert refused.refused and refused.answer == REFUSAL
    assert refused.refusal_reason == "period_not_found"
    events = list(a.ask_stream(Q))
    assert [e["event"] for e in events] == ["hits", "token", "done"]
    assert events[-1]["citations"][0]["page"] == 5


@ex
def test_llm_assistant_with_tool_call(demo_index):
    client = FakeClient(replies=[
        {"content": None, "tool_calls": [tool_call("financial_ratio", {
            "name": "capex_to_revenue",
            "values": {"capital_expenditure": -285, "revenue": 5400}})]},
        {"content": "Capex was USD 285 million [1], 5.28% of sales [2]."}])
    a = Assistant(demo_index, AssistantConfig(answer_mode="llm", embedder="lsa"), client=client)
    ans = a.ask("What was Northwind's FY2023 capex as a share of net sales?")
    assert ans.answer.startswith("Capex was USD 285 million") and ans.model == "fake-small"
    assert ans.tool_calls[0]["result"]["value"] == 5.28
    assert ans.usage == {"prompt_tokens": 200, "completion_tokens": 20}
    assert ans.cost_usd == pytest.approx((200 * 1.0 + 20 * 2.0) / 1e6)
    assert [c["ref"] for c in ans.citations] == [1, 2]
    tool_msg = client.calls[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and '"value": 5.28' in tool_msg["content"]
    assert client.calls[0]["params"]["tools"][0]["function"]["name"] == "financial_ratio"


@ex
def test_llm_assistant_streams_and_flags_bad_citations(demo_index):
    client = FakeClient(stream_parts=["USD 285 million ", "[1] [9]."])
    a = Assistant(demo_index, AssistantConfig(answer_mode="llm", embedder="lsa"), client=client)
    events = list(a.ask_stream(Q))
    assert "".join(e["text"] for e in events if e["event"] == "token") == "USD 285 million [1] [9]."
    done = events[-1]
    assert done["invalid_citations"] == [9] and done["model"] == "fake-small"
    assert done["usage"]["prompt_tokens"] == 50 and done["cost_usd"] > 0


@ex
def test_llm_refusal_is_detected(demo_index):
    client = FakeClient(replies=[{"content": REFUSAL}])
    a = Assistant(demo_index, AssistantConfig(answer_mode="llm", embedder="lsa"), client=client)
    ans = a.ask(Q)
    assert ans.refused and ans.refusal_reason == "model_refused"


@ex
def test_assistant_auto_mode_falls_back_to_extractive(demo_index):
    a = Assistant(demo_index, AssistantConfig(answer_mode="auto", embedder="lsa"))
    assert a.answer_mode() == "extractive"
    assert Assistant(demo_index, AssistantConfig(answer_mode="auto"),
                     client=FakeClient()).answer_mode() == "llm"


@ex
def test_evaluations_on_demo(demo_index, demo_questions):
    retriever = Retriever(demo_index, mode="hybrid", embedder="lsa")
    res = eval_retrieval(retriever, get_reranker("lexical"), demo_questions, scope="doc")
    assert res["recall"]["@1"] == 1.0 and res["mrr"] == 1.0 and res["misses"] == []
    a = Assistant(demo_index, AssistantConfig(answer_mode="extractive", embedder="lsa"))
    ref = eval_refusal(a, demo_questions)
    assert ref["false_refusal_rate"] == 0.0 and ref["correct_refusal_rate"] == 1.0
    out = eval_answers(a, demo_questions)
    assert out["summary"]["numeric_accuracy"] == 1.0
    assert out["summary"]["cited_evidence_page_rate"] == 1.0
    judged = eval_answers(a, demo_questions[:1], judge_client=FakeClient(replies=[
        {"content": '{"verdict": "CORRECT", "reason": "same figure"}'}]))
    assert judged["summary"]["judge_accuracy"] == 1.0
    assert judged["rows"][0]["judge_reason"] == "same figure"

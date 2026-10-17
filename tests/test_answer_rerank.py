import numpy as np
import pytest

from filing_assistant.answer import (
    REFUSAL,
    SYSTEM_PROMPT,
    build_messages,
    extractive_answer,
    ground_citations,
    is_refusal,
    parse_citations,
    should_refuse,
)
from filing_assistant.rerank import LexicalReranker, LLMReranker, NoReranker, coverage, get_reranker
from tests.conftest import FakeClient, make_hit

ex = pytest.mark.exercise
CASH = ("| (Millions) | 2023 | 2022 |\n| --- | --- | --- |\n"
        "| Purchases of property and equipment | (285) | (240) |\n"
        "| Dividends paid | (215) | (190) |")


@ex
def test_build_messages():
    hits = [make_hit("Net sales were 5,400.", page=2, title="MD&A")]
    system, user = build_messages("What were net sales?", hits)
    assert system == {"role": "system", "content": SYSTEM_PROMPT}
    assert user["role"] == "user"
    assert user["content"] == ("Context:\n[1] [ACME_2023_10K p.2] MD&A\nNet sales were 5,400."
                               "\n\nQuestion: What were net sales?")
    assert "(no passages found)" in build_messages("q?", [])[1]["content"]


@ex
def test_parse_citations():
    assert parse_citations("A [2] and [1][3], also [1, 4] and [2,5].") == [2, 1, 3, 4, 5]
    assert parse_citations("no refs, 2019 (3)") == []
    assert parse_citations("[a] [ 7 ]") == [7]


@ex
def test_ground_citations():
    hits = [make_hit("a", page=3), make_hit("b", page=9)]
    valid, invalid = ground_citations("x [2] y [5] z [0]", hits)
    assert [(c.ref, c.page) for c in valid] == [(2, 9)]
    assert invalid == [5, 0]


@ex
def test_should_refuse():
    hits = [make_hit("Northwind net sales 2023 were 5,400 million", title="Income")]
    assert should_refuse("Northwind net sales 2023?", []) == "no_evidence"
    assert should_refuse("What is Tesla's battery chemistry roadmap?", hits) == "low_coverage"
    assert should_refuse("Northwind net sales 1999?", hits) == "period_not_found"
    assert should_refuse("Northwind net sales 2023?", hits) is None
    assert should_refuse("Northwind net sales?", hits) is None


def test_refusal_and_extractive():
    assert is_refusal(f"Sorry. {REFUSAL}") and not is_refusal("Net sales were 5")
    hits = [make_hit(CASH, kind="table", title="Cash flows"), make_hit("Other text here.")]
    text, refs = extractive_answer("What was capex in FY2023?", hits)
    assert text.startswith("(285) — Purchases of property and equipment (FY2023)") and refs == [1]
    assert extractive_answer("anything", []) == (REFUSAL, [])
    sentence, _ = extractive_answer("Why did gross margin improve?",
                                    [make_hit("Gross margin improved to 40 percent as freight "
                                              "costs eased. Other things happened.")])
    assert sentence.startswith("Gross margin improved")


def test_coverage_and_lexical_reranker():
    assert coverage("capital expenditure 2023", "Capital expenditures in 2023") == 1.0
    assert coverage("the of", "anything") == 0.0
    table = make_hit(CASH, kind="table", title="Statements of Cash Flows")
    hits = [make_hit("Unrelated legal proceedings text"), table]
    ranked = LexicalReranker().rerank("What was capex in the cash flow statement for 2023?", hits)
    assert ranked[0].chunk.kind == "table" and ranked[0].rerank_score > ranked[1].rerank_score
    assert NoReranker().rerank("q", hits)[0].rerank_score == hits[0].score
    with pytest.raises(ValueError):
        get_reranker("magic")


def test_llm_reranker_uses_grades_and_survives_bad_json():
    hits = [make_hit("a"), make_hit("b"), make_hit("c")]
    client = FakeClient(replies=[{"content": '{"grades": [0, 3, 1]}'}])
    ranked = LLMReranker(client=client).rerank("q", hits)
    assert [h.chunk.text for h in ranked] == ["b", "c", "a"]
    assert client.calls[0]["params"]["response_format"] == {"type": "json_object"}
    bad = LLMReranker(client=FakeClient(replies=[{"content": "not json"}])).rerank("q", hits)
    assert len(bad) == 3
    assert LLMReranker(client=FakeClient()).rerank("q", []) == []
    assert np.isfinite(ranked[0].rerank_score)

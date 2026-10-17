"""Evaluation on FinanceBench: retrieval, refusal gate, answers, latency and cost.

- Retrieval: page-level recall@k and MRR. A question counts as found at k when any of the
  top-k passages comes from an evidence page of the right document.
- Refusal: answerable questions vs unanswerable variants (same question, fiscal year moved to
  one no filing covers). Measures correct refusals and false refusals.
- Answers: `numeric_match` for questions with a numeric gold answer (deterministic), and an
  LLM judge for all questions when a key is available.
"""

from __future__ import annotations

import json
import platform
import re
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from filing_assistant import __version__
from filing_assistant.financebench import Question
from filing_assistant.retrieve import Hit

# ---- metrics ------------------------------------------------------------------------------


def recall_at_k(hits: list[Hit], doc: str, pages: list[int], k: int) -> bool:
    """True if any of the first k hits is from `doc` and on one of the evidence `pages`.
    Questions without evidence pages count as found when any top-k hit is from `doc`."""
    # >>> SOLUTION: week-15 page-level recall@k
    for hit in hits[:k]:
        if hit.chunk.doc == doc and (not pages or hit.chunk.page in pages):
            return True
    return False
    # <<< SOLUTION


def reciprocal_rank(hits: list[Hit], doc: str, pages: list[int]) -> float:
    for rank, hit in enumerate(hits, 1):
        if hit.chunk.doc == doc and (not pages or hit.chunk.page in pages):
            return 1.0 / rank
    return 0.0


_NUM = re.compile(r"\(?-?\$?\s?\d[\d,]*(?:\.\d+)?\)?\s*%?"
                  r"(?:\s*(?:billion|million|thousand|bn|mn|m|k)\b)?", re.I)
_SCALE = {"billion": 1e9, "bn": 1e9, "million": 1e6, "mn": 1e6, "m": 1e6, "thousand": 1e3,
          "k": 1e3}


def parse_number(text: str) -> tuple[float, bool, bool] | None:
    """First number in `text` as (value, is_percent, has_unit_word); None if there is none.
    "(1,577)" → 1577.0 (the sign of parenthesised statement values is dropped),
    "$8.7 billion" → 8.7e9, "24.8%" → 24.8 with is_percent=True. Years such as 2018 that are
    followed or preceded by FY are skipped."""
    for m in _NUM.finditer(text):
        raw = m.group(0)
        start = m.start()
        if re.search(r"FY\s?$", text[max(0, start - 3):start], re.I):
            continue
        digits = re.search(r"\d[\d,]*(?:\.\d+)?", raw).group(0).replace(",", "")
        value = float(digits)
        if re.fullmatch(r"(19|20)\d{2}", digits) and not re.search(r"[$%]", raw):
            continue
        unit = re.search(r"(billion|million|thousand|bn|mn|m|k)\b", raw, re.I)
        if unit:
            value *= _SCALE[unit.group(1).lower()]
        return value, "%" in raw, bool(unit)
    return None


def numeric_match(prediction: str, gold: str, rel_tol: float = 0.01) -> bool:
    """True if the first number in `prediction` matches the first number in `gold`.

    Use parse_number on both. Compare absolute values with relative tolerance `rel_tol`.
    When exactly one side carries a unit word (million, billion...) or both lack one,
    also accept a match after scaling the prediction by 1e3, 1e6 or 1e9 (or their inverses),
    because filings report "in millions". Return False if either side has no number.
    """
    # >>> SOLUTION: week-15 numeric answer check
    p, g = parse_number(prediction), parse_number(gold)
    if p is None or g is None:
        return False
    pv, gv = abs(p[0]), abs(g[0])

    def close(a: float, b: float) -> bool:
        return abs(a - b) <= rel_tol * max(abs(b), 1e-12)

    if close(pv, gv):
        return True
    if p[2] and g[2]:
        return False
    return any(close(pv * s, gv) for s in (1e3, 1e6, 1e9, 1e-3, 1e-6, 1e-9))
    # <<< SOLUTION


def is_numeric_question(q: Question) -> bool:
    """Gold answer is essentially a number (FinanceBench metrics questions mostly are)."""
    return parse_number(q.answer) is not None and len(q.answer.split()) <= 4


# ---- retrieval -------------------------------------------------------------------------

def eval_retrieval(retriever, reranker, questions: list[Question], *, scope: str = "doc",
                   ks: tuple[int, ...] = (1, 3, 5, 10), candidates: int = 30) -> dict:
    found = {k: 0 for k in ks}
    rr, latencies, misses = [], [], []
    for q in questions:
        t0 = time.perf_counter()
        hits = retriever.search(q.question, k=candidates, docs=[q.doc] if scope == "doc" else None)
        hits = reranker.rerank(q.question, hits)
        latencies.append((time.perf_counter() - t0) * 1000)
        for k in ks:
            found[k] += recall_at_k(hits, q.doc, q.evidence_pages, k)
        rr.append(reciprocal_rank(hits, q.doc, q.evidence_pages))
        if not recall_at_k(hits, q.doc, q.evidence_pages, 5):
            misses.append({"id": q.id, "question": q.question[:160], "doc": q.doc,
                           "evidence_pages": q.evidence_pages,
                           "top3": [h.citation for h in hits[:3]]})
    n = len(questions)
    return {"questions": n, "scope": scope,
            "recall": {f"@{k}": round(found[k] / n, 4) for k in ks},
            "mrr": round(sum(rr) / n, 4),
            "latency_ms": {"p50": round(statistics.median(latencies), 2),
                           "p95": round(sorted(latencies)[int(0.95 * (n - 1))], 2)},
            "misses": misses}


# ---- refusal --------------------------------------------------------------------------

def unanswerable_variant(q: Question, year: int = 1999) -> str | None:
    """The question with every fiscal year replaced by `year` (no filing covers it), or None
    if the question names no year."""
    pattern = re.compile(r"\b(FY\s?)?(19|20)\d{2}\b|\b(FY)\s?'?\d{2}\b", re.I)
    if not pattern.search(q.question):
        return None
    return pattern.sub(lambda m: f"{m.group(1) or m.group(3) or ''}{year}", q.question)


def eval_refusal(assistant, questions: list[Question], scope: str = "doc") -> dict:
    from filing_assistant.answer import should_refuse

    false_refusals, correct_refusals, variants = 0, 0, 0
    reasons: dict[str, int] = {}
    for q in questions:
        docs = [q.doc] if scope == "doc" else None
        hits, _ = assistant.retrieve(q.question, docs)
        if should_refuse(q.question, hits, assistant.config.min_coverage):
            false_refusals += 1
        variant = unanswerable_variant(q)
        if variant:
            variants += 1
            hits, _ = assistant.retrieve(variant, docs)
            reason = should_refuse(variant, hits, assistant.config.min_coverage)
            if reason:
                correct_refusals += 1
                reasons[reason] = reasons.get(reason, 0) + 1
    return {"answerable": len(questions),
            "false_refusal_rate": round(false_refusals / len(questions), 4),
            "unanswerable_variants": variants,
            "correct_refusal_rate": round(correct_refusals / variants, 4) if variants else None,
            "refusal_reasons": reasons}


# ---- answers --------------------------------------------------------------------------

JUDGE_PROMPT = """You grade answers to questions about company filings against a gold answer.
CORRECT: same figure (allow rounding and unit wording) or same conclusion as the gold answer.
INCORRECT: different figure or conclusion, or missing the key point.
REFUSED: the answer declines to answer.
Reply with JSON only: {"verdict": "CORRECT" | "INCORRECT" | "REFUSED", "reason": "<short>"}"""


def judge(client, question: str, gold: str, answer: str, role: str = "strong") -> dict:
    out = client.complete([
        {"role": "system", "content": JUDGE_PROMPT},
        {"role": "user", "content": f"Question: {question}\nGold answer: {gold}\n"
                                    f"Answer to grade: {answer}"}],
        role=role, temperature=0, response_format={"type": "json_object"})
    try:
        verdict = json.loads(out["content"])
    except (ValueError, TypeError):
        verdict = {"verdict": "INCORRECT", "reason": "unparseable judge output"}
    verdict["usage"] = out["usage"]
    verdict["model"] = out["model"]
    return verdict


def eval_answers(assistant, questions: list[Question], *, scope: str = "doc",
                 judge_client=None, judge_role: str = "strong") -> dict:
    rows = []
    for q in questions:
        ans = assistant.ask(q.question, docs=[q.doc] if scope == "doc" else None)
        row = {"id": q.id, "type": q.type, "question": q.question, "gold": q.answer,
               "answer": ans.answer, "refused": ans.refused, "citations": ans.citations,
               "cited_evidence": any(c["doc"] == q.doc and c["page"] in q.evidence_pages
                                     for c in ans.citations),
               "numeric": is_numeric_question(q),
               "numeric_match": numeric_match(ans.answer, q.answer)
               if is_numeric_question(q) else None,
               "latency_ms": ans.timings_ms["total"], "usage": ans.usage,
               "cost_usd": ans.cost_usd, "tool_calls": len(ans.tool_calls)}
        if judge_client is not None:
            v = judge(judge_client, q.question, q.answer, ans.answer, judge_role)
            row["judge"] = v["verdict"]
            row["judge_reason"] = v.get("reason")
            row["judge_cost_usd"] = judge_client.provider.cost_usd(
                v["model"], v["usage"].get("prompt_tokens", 0),
                v["usage"].get("completion_tokens", 0))
        rows.append(row)
    numeric = [r for r in rows if r["numeric"]]
    lat = sorted(r["latency_ms"] for r in rows)
    costs = [r["cost_usd"] for r in rows if r["cost_usd"] is not None]
    summary = {
        "questions": len(rows), "scope": scope, "answer_mode": assistant.answer_mode(),
        "numeric_questions": len(numeric),
        "numeric_accuracy": round(sum(r["numeric_match"] for r in numeric) / len(numeric), 4)
        if numeric else None,
        "refusal_rate": round(sum(r["refused"] for r in rows) / len(rows), 4),
        "cited_evidence_page_rate": round(sum(r["cited_evidence"] for r in rows) / len(rows), 4),
        "latency_ms": {"p50": round(statistics.median(lat), 1),
                       "p95": round(lat[int(0.95 * (len(lat) - 1))], 1)},
        "cost_usd_per_question": round(sum(costs) / len(costs), 6) if costs else None,
    }
    if judge_client is not None:
        verdicts = [r["judge"] for r in rows]
        summary["judge_accuracy"] = round(verdicts.count("CORRECT") / len(rows), 4)
        summary["judge_counts"] = {v: verdicts.count(v) for v in sorted(set(verdicts))}
        by_type: dict[str, list[str]] = {}
        for r in rows:
            by_type.setdefault(r["type"], []).append(r["judge"])
        summary["judge_accuracy_by_type"] = {t: round(v.count("CORRECT") / len(v), 4)
                                             for t, v in sorted(by_type.items())}
    return {"summary": summary, "rows": rows}


def provenance(index, extra: dict | None = None) -> dict:
    return {"date": datetime.now(UTC).date().isoformat(), "package_version": __version__,
            "dataset": "FinanceBench open-source sample (150 questions), commit cc39aeb4afdf",
            "index": index.manifest.get("totals"), "index_created": index.manifest.get(
                "created_at"),
            "machine": f"{platform.system()} {platform.machine()}, Python "
                       f"{platform.python_version()}", **(extra or {})}


def write_json(report: dict, out_dir: Path, stem: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stem}-{report.get('date', datetime.now(UTC).date().isoformat())}.json"
    path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    return path

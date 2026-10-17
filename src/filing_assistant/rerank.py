"""Rerankers: re-order retrieved candidates with more expensive signals.

- "none":     keep the retriever's order.
- "lexical":  offline; rewards coverage of the question's terms, matching fiscal years and
              the right financial statement (cash flow, balance sheet, income statement).
- "llm":      a Mistral model grades each candidate 0-3 for usefulness (needs a key).
"""

from __future__ import annotations

import json
import re

from filing_assistant.retrieve import Hit
from filing_assistant.text import content_tokens, years

STATEMENTS = {
    "cash flow": ("cash flow", "operating activities", "investing activities"),
    "capital expenditure": ("cash flow", "property, plant"),
    "balance sheet": ("balance sheet", "total assets", "total liabilities"),
    "total assets": ("balance sheet", "total assets"),
    "inventory": ("balance sheet", "inventories"),
    "income statement": ("statement of income", "statement of operations", "net income"),
    "revenue": ("statement of income", "statement of operations", "revenue", "net sales"),
    "net income": ("statement of income", "statement of operations", "net income"),
    "operating income": ("statement of income", "statement of operations", "operating income"),
    "dividend": ("dividend",),
    "segment": ("segment",),
}


def coverage(query: str, text: str) -> float:
    """Share of the question's content tokens that appear in the text (0..1)."""
    q = set(content_tokens(query))
    if not q:
        return 0.0
    t = set(content_tokens(text))
    return len(q & t) / len(q)


def lexical_score(query: str, hit: Hit) -> float:
    text = hit.chunk.for_index().lower()
    score = coverage(query, text)
    qy = years(query)
    if qy:
        ty = years(text)
        score += 0.3 * len(qy & ty) / len(qy)
    ql = query.lower()
    for phrase, cues in STATEMENTS.items():
        if phrase in ql and any(cue in text for cue in cues):
            score += 0.3
            break
    if hit.chunk.kind == "table" and re.search(r"\b(how much|what is|what was|amount|ratio|"
                                               r"usd|\$|percent|margin)\b", ql):
        score += 0.15
    return score


class LexicalReranker:
    name = "lexical"

    def rerank(self, query: str, hits: list[Hit]) -> list[Hit]:
        n = len(hits)
        for pos, hit in enumerate(hits):
            prior = 0.5 * (n - pos) / n if n else 0.0   # keep some of the retriever's order
            hit.rerank_score = lexical_score(query, hit) + prior
        return sorted(hits, key=lambda h: -h.rerank_score)


class NoReranker:
    name = "none"

    def rerank(self, query: str, hits: list[Hit]) -> list[Hit]:
        for hit in hits:
            hit.rerank_score = hit.score
        return hits


GRADE_PROMPT = """You grade search results for a question about company filings.
For each numbered passage, give 0 (irrelevant), 1 (related), 2 (partly answers) or
3 (contains what is needed to answer). Reply with JSON only: {"grades": [g1, g2, ...]}"""


class LLMReranker:
    name = "llm"

    def __init__(self, client=None, role: str = "default", max_chars: int = 1200) -> None:
        from filing_assistant.llm import client_for
        self.client = client or client_for("mistral")
        self.role, self.max_chars = role, max_chars
        self.usage: dict = {}

    def rerank(self, query: str, hits: list[Hit]) -> list[Hit]:
        if not hits:
            return hits
        passages = "\n\n".join(f"[{i}] {h.chunk.header}\n{h.chunk.text[:self.max_chars]}"
                               for i, h in enumerate(hits, 1))
        out = self.client.complete([
            {"role": "system", "content": GRADE_PROMPT},
            {"role": "user", "content": f"Question: {query}\n\n{passages}"}],
            role=self.role, temperature=0, response_format={"type": "json_object"})
        self.usage = out["usage"]
        try:
            grades = json.loads(out["content"])["grades"]
        except (ValueError, KeyError, TypeError):
            grades = []
        n = len(hits)
        for pos, hit in enumerate(hits):
            grade = grades[pos] if pos < len(grades) and isinstance(grades[pos], int | float) \
                else 0
            hit.rerank_score = float(grade) + 0.5 * (n - pos) / n
        return sorted(hits, key=lambda h: -h.rerank_score)


def get_reranker(name: str):
    if name == "none":
        return NoReranker()
    if name == "lexical":
        return LexicalReranker()
    if name == "llm":
        return LLMReranker()
    raise ValueError(f"unknown reranker {name!r}; use none, lexical or llm")

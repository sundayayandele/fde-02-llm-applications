"""Tokenisation shared by BM25, the lexical reranker, refusal checks and evaluation."""

from __future__ import annotations

import re

STOPWORDS = frozenset("""
a an and are as at be by for from has have how in is it its of on or that the this to was
were what when which who will with does did do than then there their they them these those
give answer question based using use shown details relying response please its our we you
""".split())

_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+|\.\d+)?")
_YEAR = re.compile(r"\b(?:fy\s?)?((?:19|20)\d{2})\b", re.I)
_FY_SHORT = re.compile(r"\bfy\s?'?(\d{2})\b", re.I)


def stem(token: str) -> str:
    """Very light English stemming: plural and common verb endings only, so "flows" matches
    "flow" and "expenditures" matches "expenditure" without mangling financial terms."""
    if token.isdigit() or len(token) <= 3:
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("sses"):
        return token[:-2]
    if token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    """Lower-case, lightly stemmed word and number tokens; thousands separators removed
    ("1,577" → "1577")."""
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text.lower())
    text = re.sub(r"\bfy(?=\d{2,4}\b)", "fy ", text)        # "FY2018" → "fy", "2018"
    return [stem(t) for t in _TOKEN.findall(text)]


def content_tokens(text: str) -> list[str]:
    """Tokens without stopwords and one-letter words: what a question is actually about."""
    return [t for t in tokenize(text) if t not in STOPWORDS and len(t) > 1]


def years(text: str) -> set[int]:
    """Years mentioned, including fiscal-year forms such as FY2018, FY 2022 and FY22."""
    return {int(y) for y in _YEAR.findall(text)} | {2000 + int(y) for y in _FY_SHORT.findall(text)}

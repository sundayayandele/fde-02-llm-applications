"""Route a question to the filings it is about, before searching.

Questions name a company and usually a period ("3M ... FY2018"). Searching only that
company's filings removes most wrong-company passages, which is where whole-corpus search
fails. The router is deliberately simple and explainable: name matching plus period rules.
"""

from __future__ import annotations

import re

from filing_assistant.text import years

# Tickers and short names analysts use. Keyed by the filing-name prefix. Extend per customer.
ALIASES: dict[str, list[str]] = {
    "AMERICANEXPRESS": ["amex", "american express"],
    "JOHNSON_JOHNSON": ["jnj", "j&j", "johnson & johnson", "johnson and johnson"],
    "JPMORGAN": ["jpm", "jpmorgan", "jp morgan", "jpmorgan chase"],
    "MGMRESORTS": ["mgm"],
    "ULTABEAUTY": ["ulta"],
    "FOOTLOCKER": ["foot locker"],
    "BESTBUY": ["best buy"],
    "COCACOLA": ["coca cola", "coca-cola", "coke"],
    "GENERALMILLS": ["general mills"],
    "AMCOR": ["amcor"],
    "AMD": ["advanced micro devices"],
    "PEPSICO": ["pepsi"],
    "VERIZON": ["verizon"],
    "WALMART": ["walmart", "wal-mart"],
}

_SUFFIXES = r"\b(corporation|corp|incorporated|inc|company|co|group|holdings|plc|ltd|the)\b"


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def company_keys(company: str, doc: str) -> set[str]:
    """Normalised names a question might use: full name, name without legal suffixes, and
    the filing's name prefix (AMERICANEXPRESS)."""
    prefix = doc.split("_")[0] if not doc.startswith("JOHNSON_JOHNSON") else "JOHNSON_JOHNSON"
    keys = {_norm(company), _norm(re.sub(_SUFFIXES, " ", company, flags=re.I)), _norm(prefix)}
    keys |= {_norm(a) for a in ALIASES.get(prefix, [])}
    return {k for k in keys if len(k) >= 2}


def resolve_docs(question: str, doc_info: dict[str, dict], indexed: list[str]) -> list[str]:
    """Filings in `indexed` that the question is about; [] when no company is recognised.

    Company: any company key contained in the normalised question (longest match wins, so
    "American Express" beats "Express"). Period: when the question names years, keep filings
    whose period is one of those years or the year after (next year's report repeats the
    prior year as comparatives); fall back to all of the company's filings if none match.
    """
    q = _norm(question)
    best_len, company_docs = 0, []
    by_company: dict[str, list[str]] = {}
    for doc in indexed:
        info = doc_info.get(doc, {})
        by_company.setdefault(info.get("company", doc.split("_")[0]), []).append(doc)
    for company, docs in by_company.items():
        for key in company_keys(company, docs[0]):
            if key in q and len(key) > best_len:
                best_len, company_docs = len(key), docs
    if not company_docs:
        return []
    asked = years(question)
    if not asked:
        return sorted(company_docs)

    def period(doc: str) -> int | None:
        p = doc_info.get(doc, {}).get("doc_period")
        if p is None:
            m = re.search(r"(19|20)\d{2}", doc)
            p = int(m.group(0)) if m else None
        return p

    matched = [d for d in company_docs if period(d) in asked | {y + 1 for y in asked}]
    return sorted(matched or company_docs)

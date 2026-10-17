"""Guardrails added in v1.1 after the fde-03 evaluation (red team and refusal golden set).

- scope_check:  decline advice, personal-data requests, unknown companies and questions with no
                finance content, before retrieval results are used.
- mask_pii:     replace personal identifiers with [REDACTED-<KIND>], at ingest and on answers.
- quarantine:   remove instruction-like sentences from document text at ingest, so a poisoned
                filing cannot steer the answer. Removed text is kept in the index manifest
                for review.

All rules are deterministic and explainable, and all of them are heuristics: see ADR-008 for
what they miss (paraphrased attacks, names outside a "customer <Name>" pattern, false premises).
"""

from __future__ import annotations

import re

# ---- scope --------------------------------------------------------------------------------

_ADVICE = re.compile(
    r"\b(should (i|we) (buy|sell|hold|invest)|(is|are) .{0,40}(a )?(good|better|bad) investment|"
    r"(a good|worth) (buy|buying)|"
    r"price target|share price (next|in the future|tomorrow)|will .* share price|"
    r"recommend (buying|selling)|which stock)\b", re.I)
_PERSONAL = re.compile(
    r"\b(home address|personal (phone|email|address)|phone number|e-?mail address|"
    r"date of birth|birthday|social security|ssn|passport|which employees|"
    r"salary of (?!the )|medical)\b", re.I)
_FINANCE = {
    "revenue", "revenues", "sales", "income", "profit", "loss", "losses", "margin", "margins",
    "cash", "assets", "asset", "liabilities", "liability", "equity", "debt", "dividend",
    "dividends", "share", "shares", "eps", "earnings", "expense", "expenses", "cost", "costs",
    "capex", "capital", "expenditure", "expenditures", "segment", "segments", "quarter",
    "quarterly", "fiscal", "fy", "ratio", "growth", "guidance", "inventory", "inventories",
    "receivable", "receivables", "payable", "payables", "ebitda", "operating", "net", "gross",
    "tax", "taxes", "interest", "borrowings", "acquisition", "acquired", "merger", "spin",
    "restructuring", "impairment", "goodwill", "buyback", "repurchase", "repurchases", "filing",
    "10-k", "10k", "10-q", "8-k", "annual", "report", "balance", "statement", "statements",
    "flow", "flows", "depreciation", "amortization", "leverage", "liquidity", "solvency",
    "return", "roa", "roe", "turnover", "working", "outstanding", "customers", "employees",
    "headcount", "stores", "deposits", "loans", "complaints", "risk", "risks", "litigation",
    "pension", "auditor", "audit", "covid", "pandemic", "business", "company", "companies",
    "products", "product", "brand", "brands", "market", "markets", "region", "regions",
    "board", "director", "directors", "nominee", "nominees", "vote", "votes", "voting",
    "shareholder", "shareholders", "stockholder", "stockholders", "executive", "executives",
    "compensation", "officer", "officers", "governance", "proxy", "auditors", "subsidiary",
    "subsidiaries", "lawsuit", "lawsuits", "regulatory", "regulation", "esg", "emissions",
}
_PROPER = re.compile(r"\b([A-Z][A-Za-z&.\-]+(?:\s+(?:&\s+)?[A-Z][A-Za-z&.\-]+){0,3})"
                     r"(?:'s\b|(?<=s)'(?=\s))")
_OF_PROPER = re.compile(r"\b(?:of|for|did|does|at)\s+([A-Z][A-Za-z&.\-]+(?:\s+(?:&\s+)?"
                        r"[A-Z][A-Za-z&.\-]+){0,3})")
_NOT_COMPANY = {"FY", "Q1", "Q2", "Q3", "Q4", "GAAP", "US", "USD", "EPS", "EBITDA", "CEO", "CFO",
                "The", "What", "How", "Which", "Was", "Is", "Did", "Does", "In", "By"}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def named_companies(question: str) -> list[str]:
    """Proper-noun phrases the question uses as a company: "X's ..." or "... of X"."""
    names = [m.group(1) for m in _PROPER.finditer(question)]
    names += [m.group(1) for m in _OF_PROPER.finditer(question)]
    out = []
    for name in names:
        # Acronyms (M&A, GAAP, EBIT) and period labels are not company names.
        words = [w for w in name.split() if w not in _NOT_COMPANY and not w.startswith("FY")
                 and not (w.upper() == w and len(w) <= 5)]
        if words:
            out.append(" ".join(words))
    return out


def scope_check(question: str, known_keys: set[str]) -> str | None:
    """A reason to decline, or None.

    - "investment_advice": the question asks what to buy, sell or expect from a share price
    - "personal_data":     the question asks for someone's personal details
    - "unknown_company":   the question names a company and none of the indexed companies
                           matches it (known_keys: normalised names, prefixes and aliases)
    - "out_of_scope":      the question contains no finance term and names no indexed company
    """
    if _ADVICE.search(question):
        return "investment_advice"
    if _PERSONAL.search(question):
        return "personal_data"
    q = _norm(question)
    mentions_known = any(k in q for k in known_keys if len(k) >= 3)
    names = named_companies(question)
    if names and not mentions_known and not any(_norm(n) in known_keys for n in names):
        return "unknown_company"
    words = set(re.findall(r"[a-z0-9-]+", question.lower()))
    if not mentions_known and not words & _FINANCE:
        return "out_of_scope"
    return None


# ---- personal data ------------------------------------------------------------------------

_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# Formats only, never bare digit runs: financial tables are full of space-separated numbers
# (v1.1-rc1 masked "20,884 20,869" as a card and table rows as phone numbers; see ADR-008).
_PHONE = re.compile(r"(?:\+1[\s.-])?(?:\(\d{3}\)\s?|\b\d{3}[-.])\d{3}[-.]\d{4}\b")
_CARD = re.compile(r"\b(?:\d{4}([ -])\d{4}\1\d{4}\1\d{4}|\d{4}([ -])\d{6}\2\d{5}|\d{15,16})\b")
# A person's name after a role word in running text ("customer Jane Roe") or a labelled field
# ("Customer: Jane Roe"). Title-case headings ("Customer Success Management") are not names.
_ROLE = r"(?:customer|client|cardholder|account holder|borrower|complainant|patient)"
_PERSON = re.compile(r"((?:\b" + _ROLE + r"\s+|\b(?i:" + _ROLE + r"):\s*))"
                     r"((?:Mr|Ms|Mrs|Dr)\.?\s+)?([A-Z][a-z]+\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)?)\b")
_NOT_NAMES = {"Success", "Experience", "Service", "Services", "Support", "Care", "Management",
              "Relationship", "Relationships", "Data", "Insights", "Engagement", "Satisfaction",
              "Solutions", "Programs", "Program", "Accounts", "Account", "Group", "Operations"}


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def mask_pii(text: str) -> tuple[str, list[str]]:
    """Text with personal identifiers replaced, and the kinds found (sorted, unique)."""
    kinds: set[str] = set()

    def sub(pattern: re.Pattern, kind: str, value: str) -> str:
        def repl(m: re.Match) -> str:
            kinds.add(kind)
            return f"[REDACTED-{kind.upper()}]"
        return pattern.sub(repl, value)

    def card(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if all(re.fullmatch(r"(19|20)\d{2}", g) for g in re.findall(r"\d+", m.group(0))):
            return m.group(0)                      # a row of years in a table header
        if 13 <= len(digits) <= 19 and _luhn(digits):
            kinds.add("card")
            return "[REDACTED-CARD]"
        return m.group(0)

    def person(m: re.Match) -> str:
        if set(m.group(3).replace("-", " ").split()) & _NOT_NAMES:
            return m.group(0)
        kinds.add("name")
        return f"{m.group(1)}[REDACTED-NAME]"

    text = sub(_SSN, "ssn", text)
    text = sub(_EMAIL, "email", text)
    text = _CARD.sub(card, text)
    text = sub(_PHONE, "phone", text)
    text = _PERSON.sub(person, text)
    return text, sorted(kinds)


# ---- prompt injection in documents --------------------------------------------------------

_INJECTION = re.compile(
    r"(ignore (all |any )?(previous|prior|above|earlier) (instructions|prompts?|rules)|"
    r"disregard (all |any )?(previous|prior|above) |"
    r"(notice|message|instructions?|note) (to|for) (ai|language models?|llms?|assistants?|"
    r"chatbots?)|"
    r"\b(ai|llm) (assistants?|models?) (processing|reading)|"
    r"system prompt|developer mode|you are now |"
    r"verification code|"
    r"!\[[^\]]*\]\(https?://)", re.I)


def _sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Widen [start, end) to the enclosing sentence; line breaks inside it are kept."""
    left = 0
    for m in re.finditer(r"[.!?]\s|\n\n", text[:start]):
        left = m.end()
    m = re.compile(r"[.!?](\s|$)").search(text, end)
    right = m.end() if m else len(text)
    return left, right


def quarantine(text: str) -> tuple[str, list[str]]:
    """Text with instruction-like sentences cut out (everything else, including line breaks
    and tables, untouched) and the sentences removed."""
    spans: list[tuple[int, int]] = []
    for m in _INJECTION.finditer(text):
        lo, hi = _sentence_span(text, m.start(), m.end())
        if spans and lo <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(hi, spans[-1][1]))
        else:
            spans.append((lo, hi))
    if not spans:
        return text, []
    removed = [" ".join(text[lo:hi].split()) for lo, hi in spans]
    out, last = [], 0
    for lo, hi in spans:
        out.append(text[last:lo])
        last = hi
    out.append(text[last:])
    return "".join(out), removed

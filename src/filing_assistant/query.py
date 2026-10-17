"""Query rewriting for retrieval: drop instruction boilerplate, add filing vocabulary.

Analysts ask "what was capex?"; filings say "Purchases of property, plant and equipment".
A small, reviewable glossary closes that gap without a model call. The original question
is still what the answering model sees.
"""

from __future__ import annotations

import re

BOILERPLATE = [
    r"assume that you are an? [^.:?]*?(?:analyst|investor)[^.:?]*[.:]?",
    r"answer the following question[^.:?]*[.:]",
    r"(?:please )?give a response to the question[^.?]*[.?]?",
    r"(?:please )?(?:by )?(?:primarily )?(?:using|relying on) (?:the )?(?:information|details|data)"
    r" (?:that is )?shown (?:in|within) the",
    r"answer in usd [a-z]+[^.?]*[.?]?",
    r"round your answer to [^.?]*[.?]?",
    r"calculate (?:what was|the)",
    r"if [^.?]* is not (?:a )?(?:useful|relevant) [^.?]*[.?]",
    r"(?:please )?state that and explain why\.?",
]

GLOSSARY: dict[str, str] = {
    r"\bcapex\b|capital expenditures?": "purchases of property plant and equipment capital "
                                        "expenditures additions",
    r"\bpp&?e\b|\bppne\b|\bppe\b": "property plant and equipment net",
    r"cash flow statement|statement of cash flows?": "consolidated statement of cash flows "
                                                     "operating investing financing activities",
    r"income statement|\bp&l\b|statement of income|statement of operations":
        "consolidated statement of income operations net sales revenue",
    r"balance sheet": "consolidated balance sheet total assets liabilities equity",
    r"\bcogs\b|cost of goods sold": "cost of sales cost of goods sold",
    r"operating margin": "operating income revenue net sales",
    r"gross margin": "gross profit gross margin net sales cost of sales",
    r"quick ratio|current ratio|liquidity": "total current assets total current liabilities "
                                            "inventories cash",
    r"\bebitda\b": "operating income depreciation amortization",
    r"free cash flow": "net cash provided by operating activities purchases of property",
    r"dividend payout": "dividends paid net income",
    r"\bdpo\b|days payable": "accounts payable cost of sales",
    r"\bdso\b|days sales outstanding": "accounts receivable revenue",
    r"inventory turnover": "inventories cost of sales",
    r"working capital": "total current assets total current liabilities",
    r"\broa\b|return on assets": "net income total assets",
    r"\broe\b|return on equity": "net income total shareholders equity",
    r"capital[- ]intensive": "purchases of property plant and equipment total assets "
                             "depreciation",
    r"effective tax rate": "provision for income taxes effective tax rate income before taxes",
    r"\bm&a\b|acquisitions?": "acquisitions business combinations",
    r"segment": "segment operating results",
    r"debt securities|registered to trade": "securities registered pursuant to section 12(b) "
                                            "trading symbol exchange",
}


def strip_boilerplate(question: str) -> str:
    text = question
    for pattern in BOILERPLATE:
        text = re.sub(pattern, " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip() or question


def rewrite(question: str) -> str:
    """Retrieval query: question without boilerplate, plus glossary expansions."""
    core = strip_boilerplate(question)
    extra = [expansion for pattern, expansion in GLOSSARY.items()
             if re.search(pattern, question, re.I)]
    return " ".join([core, *extra])

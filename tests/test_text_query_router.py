from filing_assistant.query import rewrite, strip_boilerplate
from filing_assistant.router import company_keys, resolve_docs
from filing_assistant.text import content_tokens, stem, tokenize, years


def test_tokenize_and_stem():
    assert tokenize("Cash Flows of $1,577 million in FY2018") == \
        ["cash", "flow", "of", "1577", "million", "in", "fy", "2018"]
    assert stem("expenditures") == "expenditure" and stem("liabilities") == "liability"
    assert stem("business") == "business" and stem("gas") == "gas" and stem("2018") == "2018"
    assert content_tokens("What is the revenue of 3M?") == ["revenue", "3m"]


def test_years():
    assert years("FY2018 vs FY 2017 and 2016, not 12018") == {2016, 2017, 2018}
    assert years("From FY21 to FY22") == {2021, 2022}


def test_rewrite_strips_boilerplate_and_expands():
    q = ("Assume that you are a public equities analyst. Answer the following question by "
         "primarily using information that is shown in the balance sheet: what is the year "
         "end FY2018 net PPNE for 3M?")
    core = strip_boilerplate(q)
    assert "analyst" not in core and "PPNE" in core
    assert "property plant and equipment net" in rewrite(q)
    assert "purchases of property plant and equipment" in rewrite("What was capex?")
    assert rewrite("hello") == "hello"


INFO = {"3M_2018_10K": {"company": "3M", "doc_period": 2018},
        "3M_2022_10K": {"company": "3M", "doc_period": 2022},
        "AMERICANEXPRESS_2022_10K": {"company": "American Express", "doc_period": 2022},
        "JOHNSON_JOHNSON_2022_10K": {"company": "Johnson & Johnson", "doc_period": 2022},
        "CORNING_2021_10K": {"company": "Corning", "doc_period": 2021}}


def test_company_keys():
    keys = company_keys("American Express Company", "AMERICANEXPRESS_2022_10K")
    assert {"americanexpress", "amex"} <= keys


def test_resolve_docs():
    docs = sorted(INFO)
    assert resolve_docs("3M capex in FY2018?", INFO, docs) == ["3M_2018_10K"]
    assert resolve_docs("3M capex in FY2021?", INFO, docs) == ["3M_2022_10K"]
    assert resolve_docs("Is 3M capital intensive?", INFO, docs) == ["3M_2018_10K", "3M_2022_10K"]
    assert resolve_docs("3M sales in FY2010?", INFO, docs) == ["3M_2018_10K", "3M_2022_10K"]
    assert resolve_docs("Does AMEX have improving margins?", INFO, docs) == \
        ["AMERICANEXPRESS_2022_10K"]
    assert resolve_docs("JnJ inventory turnover FY2022", INFO, docs) == \
        ["JOHNSON_JOHNSON_2022_10K"]
    assert resolve_docs("What drove SG&A down?", INFO, docs) == []

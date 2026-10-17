import asyncio
import json

import pytest

from filing_assistant.mcp_server import build_server
from filing_assistant.tools import RATIOS, RatioError, compute_ratio, list_filings, run_tool

ex = pytest.mark.exercise


@ex
def test_compute_ratio():
    assert compute_ratio("gross_margin", {"gross_profit": 2160, "revenue": 5400})["value"] == 40.0
    r = compute_ratio("quick_ratio", {"current_assets": 2300, "inventories": 1150,
                                      "current_liabilities": 1400})
    assert r["value"] == 0.82 and r["unit"] == "x"
    assert compute_ratio("capex_to_revenue", {"capital_expenditure": -285,
                                              "revenue": 5400})["value"] == 5.28
    assert compute_ratio("growth", {"current": 5400, "previous": 5000})["value"] == 8.0
    assert compute_ratio("growth", {"current": -5, "previous": -10})["value"] == 50.0


@ex
@pytest.mark.parametrize(("name", "values", "match"), [
    ("magic", {}, "unknown ratio"),
    ("gross_margin", {"revenue": 1}, "needs"),
    ("current_ratio", {"current_assets": 1, "current_liabilities": 0}, "zero"),
])
def test_compute_ratio_errors(name, values, match):
    with pytest.raises(RatioError, match=match):
        compute_ratio(name, values)


@ex
def test_run_tool():
    assert run_tool("financial_ratio", {"name": "net_margin",
                                        "values": {"net_income": 585, "revenue": 5400}})[
        "value"] == 10.83
    assert "error" in run_tool("financial_ratio", {"name": "nope"})
    assert "error" in run_tool("delete_everything", {})


def test_list_filings():
    info = {"ACME_2023_10K": {"company": "Acme", "doc_period": 2023, "doc_type": "10k"},
            "ACME_2023Q2_10Q": {"company": "Acme", "doc_period": 2023, "doc_type": "10q"}}
    docs = sorted(info) + ["OTHER_2021_8K"]
    assert len(list_filings(info, docs)) == 3
    assert [f["doc"] for f in list_filings(info, docs, company="acme", doc_type="10q")] == \
        ["ACME_2023Q2_10Q"]
    assert [f["doc"] for f in list_filings(info, docs, year=2021)] == ["OTHER_2021_8K"]
    assert set(RATIOS) >= {"gross_margin", "growth"}


def _call(server, tool, args):
    """Tool result as Python data: one JSON block, or a list when the tool returned a list."""
    result = asyncio.run(server.call_tool(tool, args))
    assert not result.is_error
    data = [json.loads(block.text) for block in result.content]
    if len(data) == 1 and not isinstance(data[0], list) and tool not in {
            "filing_lookup", "search_filings"}:
        return data[0]
    return data[0] if len(data) == 1 and isinstance(data[0], list) else data


def test_mcp_lists_tools(tmp_path):
    server = build_server(tmp_path, tmp_path)
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {"financial_ratio", "list_ratios", "filing_lookup", "search_filings",
                     "get_page"}
    assert "gross_margin" in _call(server, "list_ratios", {})


@ex
def test_mcp_tools_on_demo_index(demo_index, tmp_path):
    server = build_server(tmp_path, tmp_path, index=demo_index)
    assert _call(server, "financial_ratio", {"name": "gross_margin", "values": {
        "gross_profit": 1, "revenue": 4}})["value"] == 25.0
    assert "error" in _call(server, "financial_ratio", {"name": "nope", "values": {}})
    filings = _call(server, "filing_lookup", {"company": "northwind"})
    assert sorted(f["doc"] for f in filings) == ["NORTHWIND_2023_10K", "NORTHWIND_2023_EXHIBIT"]
    hits = _call(server, "search_filings", {"query": "Northwind capex 2023", "k": 2})
    assert hits[0]["doc"] == "NORTHWIND_2023_10K" and len(hits) <= 2
    page = _call(server, "get_page", {"doc": "NORTHWIND_2023_10K", "page": 5})
    assert page["found"] and "285" in page["text"]

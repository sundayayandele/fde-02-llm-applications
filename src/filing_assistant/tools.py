"""Financial tools shared by the assistant (LLM function calling) and the MCP server.

Deterministic arithmetic belongs in code, not in the model: the model picks the inputs from
cited evidence, the tool computes.
"""

from __future__ import annotations

import re
from pathlib import Path

RATIOS: dict[str, dict] = {
    "gross_margin": {"inputs": ["gross_profit", "revenue"], "unit": "%",
                     "formula": "gross_profit / revenue × 100"},
    "operating_margin": {"inputs": ["operating_income", "revenue"], "unit": "%",
                         "formula": "operating_income / revenue × 100"},
    "net_margin": {"inputs": ["net_income", "revenue"], "unit": "%",
                   "formula": "net_income / revenue × 100"},
    "current_ratio": {"inputs": ["current_assets", "current_liabilities"], "unit": "x",
                      "formula": "current_assets / current_liabilities"},
    "quick_ratio": {"inputs": ["current_assets", "inventories", "current_liabilities"],
                    "unit": "x", "formula": "(current_assets − inventories) / current_liabilities"},
    "debt_to_equity": {"inputs": ["total_debt", "total_equity"], "unit": "x",
                       "formula": "total_debt / total_equity"},
    "return_on_assets": {"inputs": ["net_income", "average_total_assets"], "unit": "%",
                         "formula": "net_income / average_total_assets × 100"},
    "capex_to_revenue": {"inputs": ["capital_expenditure", "revenue"], "unit": "%",
                         "formula": "capital_expenditure / revenue × 100"},
    "growth": {"inputs": ["current", "previous"], "unit": "%",
               "formula": "(current − previous) / |previous| × 100"},
    "dividend_payout": {"inputs": ["dividends", "net_income"], "unit": "%",
                        "formula": "dividends / net_income × 100"},
}


class RatioError(ValueError):
    pass


def compute_ratio(name: str, values: dict[str, float], decimals: int = 2) -> dict:
    """Compute a named ratio from `values`.

    - Unknown name → RatioError listing the known names.
    - Missing inputs (see RATIOS[name]["inputs"]) → RatioError naming them.
    - A zero denominator → RatioError.
    - Capital expenditure is often shown negative in cash flow statements: use its absolute value.
    Return {"ratio": name, "value": rounded value, "unit", "formula", "inputs": values used}.
    """
    # >>> SOLUTION: week-14 financial ratio calculator
    if name not in RATIOS:
        raise RatioError(f"unknown ratio {name!r}; known: {sorted(RATIOS)}")
    spec = RATIOS[name]
    missing = [k for k in spec["inputs"] if k not in values]
    if missing:
        raise RatioError(f"{name} needs {missing}")
    v = {k: float(values[k]) for k in spec["inputs"]}
    if "capital_expenditure" in v:
        v["capital_expenditure"] = abs(v["capital_expenditure"])
    pct = spec["unit"] == "%"
    if name == "quick_ratio":
        num, den = v["current_assets"] - v["inventories"], v["current_liabilities"]
    elif name == "growth":
        num, den = v["current"] - v["previous"], abs(v["previous"])
    else:
        first, second = spec["inputs"]
        num, den = v[first], v[second]
    if den == 0:
        raise RatioError(f"{name}: denominator is zero")
    value = num / den * (100 if pct else 1)
    return {"ratio": name, "value": round(value, decimals), "unit": spec["unit"],
            "formula": spec["formula"], "inputs": v}
    # <<< SOLUTION


def list_filings(doc_info: dict[str, dict], indexed: list[str], company: str | None = None,
                 year: int | None = None, doc_type: str | None = None) -> list[dict]:
    """Filings known to the index, filtered by company (substring), period and type."""
    out = []
    for doc in indexed:
        info = doc_info.get(doc, {})
        period = info.get("doc_period")
        if period is None:
            m = re.search(r"(19|20)\d{2}", doc)
            period = int(m.group(0)) if m else None
        row = {"doc": doc, "company": info.get("company", doc.split("_")[0]),
               "period": period, "type": info.get("doc_type", doc.rsplit("_", 1)[-1].lower()),
               "sector": info.get("gics_sector"), "source": info.get("doc_link")}
        if company and company.lower() not in (row["company"] or "").lower() \
                and company.lower() not in doc.lower():
            continue
        if year and row["period"] != year:
            continue
        if doc_type and doc_type.lower() not in str(row["type"]).lower():
            continue
        out.append(row)
    return out


TOOL_SPECS = [{
    "type": "function",
    "function": {
        "name": "financial_ratio",
        "description": "Compute a financial ratio or growth rate exactly. Use it instead of "
                       "doing arithmetic yourself. Inputs must come from the cited context.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "enum": sorted(RATIOS)},
                "values": {"type": "object", "additionalProperties": {"type": "number"},
                           "description": "Inputs by name, e.g. {\"gross_profit\": 1, "
                                          "\"revenue\": 4}. See the ratio's required inputs."},
            },
            "required": ["name", "values"],
        },
    },
}]


def run_tool(name: str, arguments: dict, data_dir: Path | None = None) -> dict:
    if name == "financial_ratio":
        try:
            return compute_ratio(arguments.get("name", ""), arguments.get("values") or {})
        except RatioError as e:
            return {"error": str(e), "known_ratios": {k: r["inputs"] for k, r in RATIOS.items()}}
    return {"error": f"unknown tool {name!r}"}

"""MCP tool server: lets any MCP client (Claude Desktop, Claude Code, Le Chat, an agent
framework) use the filing index and the ratio calculator.

    filing-assistant mcp                                   # stdio (desktop clients)
    filing-assistant mcp --transport streamable-http       # HTTP on :8000/mcp

Tools are read-only: they search and compute, they never change the index.
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from filing_assistant.tools import RATIOS, RatioError, compute_ratio, list_filings


def build_server(index_dir: Path, data_dir: Path, index=None) -> MCPServer:
    mcp = MCPServer("filing-assistant", instructions=(
        "Search public company filings (10-K, 10-Q, 8-K, earnings releases) and compute "
        "financial ratios exactly. Cite results as <doc> p.<page>."))
    state: dict = {"index": index}
    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    def get_index():
        if state["index"] is None:
            from filing_assistant.index import load
            state["index"] = load(index_dir)
        return state["index"]

    @mcp.tool(annotations=read_only)
    def financial_ratio(name: str, values: dict[str, float]) -> dict:
        """Compute a financial ratio exactly. `name` is one of: gross_margin, operating_margin,
        net_margin, current_ratio, quick_ratio, debt_to_equity, return_on_assets,
        capex_to_revenue, growth, dividend_payout. `values` holds the named inputs
        (call list_ratios to see them)."""
        try:
            return compute_ratio(name, values)
        except RatioError as e:
            return {"error": str(e)}

    @mcp.tool(annotations=read_only)
    def list_ratios() -> dict:
        """Ratios the calculator knows, with their required inputs and formulas."""
        return {k: {"inputs": v["inputs"], "formula": v["formula"], "unit": v["unit"]}
                for k, v in RATIOS.items()}

    @mcp.tool(annotations=read_only)
    def filing_lookup(company: str | None = None, year: int | None = None,
                      doc_type: str | None = None) -> list[dict]:
        """Filings in the index, filtered by company name (substring), period and type
        (10k, 10q, 8k, earnings)."""
        idx = get_index()
        return list_filings(idx.doc_info, idx.docs, company, year, doc_type)

    @mcp.tool(annotations=read_only)
    def search_filings(query: str, k: int = 5, doc: str | None = None) -> list[dict]:
        """Search the filings (BM25 + lexical rerank, routed by company and year when no
        `doc` is given). Returns passages with doc, page and text for citation."""
        from filing_assistant.pipeline import Assistant, AssistantConfig
        idx = get_index()
        assistant = Assistant(idx, AssistantConfig(mode="hybrid" if idx.dense else "bm25",
                                                   context=max(1, min(k, 20)),
                                                   answer_mode="extractive"))
        hits, _ = assistant.retrieve(query, [doc] if doc else None)
        return [{"doc": h.chunk.doc, "page": h.chunk.page, "title": h.chunk.title,
                 "kind": h.chunk.kind, "text": h.chunk.text[:2000]} for h in hits]

    @mcp.tool(annotations=read_only)
    def get_page(doc: str, page: int) -> dict:
        """Full extracted text of one filing page (1-based page number)."""
        idx = get_index()
        text = idx.page_text(doc, page)
        return {"doc": doc, "page": page, "text": text or "", "found": bool(text)}

    return mcp


def main() -> None:  # pragma: no cover - console entry point
    from filing_assistant.config import get_settings
    s = get_settings()
    build_server(Path(s.index_dir), Path(s.data_dir)).run()

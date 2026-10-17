# Week 14: Grounding: refusal, tools and MCP

**Goal:** make the assistant refuse when evidence is weak, do arithmetic exactly, and expose its tools to other AI clients.

## Brief

Compliance's rule: never a figure without a source, never arithmetic done "in the model's head", and "I can't answer that" is an acceptable answer. The research desk also wants the tools inside Claude Desktop.

## Concepts

Refusal before generation; coverage and period checks; thresholds tuned on dev, reported on test; function calling (tool specs, tool messages, loops with limits); deterministic tools; the Model Context Protocol (tools, transports, read-only annotations).

## Steps

1. Implement `should_refuse(question, hits, min_coverage)` in `answer.py`: `no_evidence`, `low_coverage`, `period_not_found`, in that order.
2. Implement `compute_ratio(name, values)` in `tools.py` from `RATIOS`: errors for unknown names, missing inputs and zero denominators; capex as an absolute value.
3. `pytest tests/test_answer_rerank.py tests/test_tools_mcp.py tests/test_pipeline_eval.py -m exercise`.
4. Tune the gate on the dev half: `for t in 0.1 0.2 0.3 0.35; do filing-assistant eval-refusal --split dev --min-coverage $t; done`. Pick one, then run the **test** half once with it.
5. Read `pipeline.py` `_llm_answer`: the tool loop. With a key, ask "What was Northwind's FY2023 capex as a share of net sales?" with `--json` and find the tool call.
6. Connect the MCP server to Claude Desktop (README snippet), or run `npx @modelcontextprotocol/inspector filing-assistant mcp`, and call `search_filings` and `financial_ratio`.

## Check

```bash
make exercises        # everything except week 15
filing-assistant eval-refusal --split test
```

## Evidence

Your threshold sweep on dev, the single test-half result, a tool-call trace, and a screenshot of the MCP tools in a client.

## Stretch

Add a `period_mismatch` check: the question asks for FY2022 but every passage comes from a filing whose period is FY2018 or earlier. Measure the change on dev.

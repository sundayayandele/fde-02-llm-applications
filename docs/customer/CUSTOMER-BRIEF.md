# Customer brief: answers from filings that an analyst can trust

> Fictional engagement for the lab. "Harbour Capital" is an invented asset manager. Public
> filings and FinanceBench stand in for the customer's own research library.

## Situation

Harbour Capital's analysts spend hours a week finding figures in 10-Ks and earnings releases: capex, margins, segment growth, legal proceedings. A pilot with a generic chatbot was stopped after it produced a convincing but wrong capex figure for a holding. Compliance now requires that any assistant **shows its source for every number** and **declines when it cannot find one**.

## What they asked for

1. Ask in plain English; get a short answer with the page each figure comes from.
2. A clear "I can't answer that from the filings" when the evidence is not there.
3. Exact arithmetic for ratios and growth rates, with the inputs shown.
4. Use from their existing tools: the web UI, and Claude Desktop through MCP.
5. EU data residency for prompts that may later include internal research notes.
6. A measured comparison against a public benchmark before any rollout.

## Success criteria (agreed)

| Criterion | Target | How we show it |
| --- | --- | --- |
| Evidence found | Recall@5 ≥ 0.6 in the realistic (routed) setting | FinanceBench retrieval report |
| No false refusals | ≤ 5% of answerable questions refused | Refusal report, test half |
| Refuses the unanswerable | ≥ 85% of out-of-period questions refused | Refusal report, test half |
| Answer accuracy | Agreed after the first Mistral run (benchmark is hard: many questions need multi-step arithmetic) | LLM-judged accuracy, test half, spot-checked by an analyst |
| Every answer cited | 100% of non-refusals cite at least one page; 0 invalid citations | API fields, `InvalidCitations` alert |
| Latency | p95 < 10 s per answer | Evaluation report, `answer_seconds` metric |
| Cost | < USD 0.01 per question | Token usage × price |

Measured so far (2026-10-15, no LLM): routed recall@5 0.600; refusal test half 0.0% false and 87.5% correct.

## Out of scope for this phase

Conversation memory, write actions, internal documents with personal data (needs fde-05's self-hosted model), automated evaluation of the judge itself (fde-03).

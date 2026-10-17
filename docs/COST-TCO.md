# Cost and total cost of ownership

> **Prices are assumptions.** Unit prices are approximate list prices remembered for mid-2026,
> written without live access to pricing pages. They are in `config/providers.yaml` (`prices`)
> and drive the `cost_usd` fields. Verify on https://mistral.ai/pricing and update them before
> quoting. Token counts come from the API's usage fields and are measured.

## LLM cost per question (estimate until measured)

| Item | Tokens (typical) | Assumed price (USD per 1M tokens) | USD per question |
| --- | --- | --- | --- |
| Answer, Mistral Small: 6 passages + prompt + question | ~4,000–6,000 in, ~150 out | 0.10 in / 0.30 out | ~0.0005 |
| Tool round (when used) | +~6,000 in, +~50 out | same | +~0.0006 |
| LLM reranker (optional) | ~6,000 in, ~30 out | same | +~0.0006 |
| Judge, Mistral Large (evaluation only) | ~400 in, ~60 out | 2.00 in / 6.00 out | ~0.0012 |

One-off indexing with `mistral-embed`: 49,331 chunks, roughly 10–15 million tokens at an assumed USD 0.10 per million, so about USD 1–2. Offline LSA costs nothing.

A full FinanceBench evaluation (test half, 71 questions, answers + judge) is therefore in the order of USD 0.10–0.20. The `eval-answers` report records the measured `cost_usd_per_question`: copy it into the README table.

## Infrastructure per month if left running (estimates)

| Cloud | Shape | Approximate monthly |
| --- | --- | --- |
| AWS | Fargate 0.5 vCPU + 2 GB 24×7, public IPv4, logs | ~USD 25 |
| Azure | Container Apps 1 vCPU / 2 GiB, scale to zero, ACR Basic | ~USD 5–10 |
| GCP | Cloud Run 1 vCPU / 2 GiB, scale to zero | ~USD 0–3 |

## Where the money goes at scale

At pilot volume (hundreds of questions a day) LLM cost is a few dollars a month; infrastructure and people dominate. At thousands of questions a day, prompt tokens dominate. Levers, in order: fewer and shorter passages (better reranking), cache answers to repeated questions, route simple lookups to the extractive path, then a smaller or self-hosted model (fde-05).

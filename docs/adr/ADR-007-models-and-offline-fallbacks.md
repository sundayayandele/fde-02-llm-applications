# ADR-007: Mistral Small answers, Mistral Large judges, offline fallbacks everywhere

- **Status:** Accepted (pin exact model IDs when the first measured run is recorded)
- **Date:** 2026-10-15
- **Deciders:** Sunday Ayandele (owner)

## Context

The series defaults to Mistral (EU-hosted, allowed for regulated data in `providers.yaml`). Answers must be cheap per question. The judge should be stronger than the model it grades. Learners and CI must be able to run everything without a key.

## Options considered

| Role | Option | Why / why not |
| --- | --- | --- |
| Answering | `mistral-small-latest` | Low cost, tool calling, JSON mode |
| Answering | `mistral-large-latest` | Stronger reasoning for multi-step metrics; about 20× the token price (assumed prices) |
| Embeddings | `mistral-embed` | Same provider and residency; about USD 1–2 to embed all 49k chunks (assumed price) |
| Judge | `mistral-large-latest` | Stronger than the answerer; JSON verdicts |
| Offline answering | Extractive baseline | Free and deterministic, but cannot compute ratios (9.4% numeric accuracy) |
| Offline dense | LSA | Free, sovereign; recall comparable to BM25 here |

## Decision

Answer with Mistral Small and tools, judge with Mistral Large, embed with `mistral-embed` when a key is present. Fall back to the extractive answerer and LSA without a key (`ANSWER_MODE=auto`). The `-latest` aliases move. Record the model ID returned by the API in every evaluation report, and pin exact IDs in `providers.yaml` before a customer pilot.

## Consequences

- LLM-judge accuracy is an estimate. `fde-03` calibrates the judge against human labels.
- Switching to Large for answering is one setting (`LLM_ROLE=strong`). Measure the quality gain against the cost before doing it.
- The other providers (OpenAI, DeepSeek, Qwen, Kimi) work for public filings. Their `regulated_data_allowed: false` setting blocks them for customer data.

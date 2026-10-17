# System card: filing assistant 1.0.0

| Field | Value |
| --- | --- |
| System | Retrieval-augmented question answering over company filings, with refusal and exact-arithmetic tool |
| Models | Answers: `mistral-small-latest` (configurable); judge: `mistral-large-latest`; embeddings: `mistral-embed` or offline LSA; offline extractive answerer when no key |
| Corpus | FinanceBench open-source sample: 84 filings, 12,013 pages, 49,331 chunks (commit `cc39aeb4afdf`); plus the fictional Northwind demo filings |
| Intended use | Help analysts find and verify figures and statements in public filings, with page citations |
| Not intended for | Investment advice; decisions without human review; documents not in the index; personal or regulated data on providers not allowed to receive it |
| Measured (2026-10-15) | Routed retrieval recall@5 0.600 (recall@10 0.680); refusal on held-out half: 0.0% false, 87.5% correct; extractive baseline numeric accuracy 9.4% |
| Pending | Mistral answer accuracy (LLM judge, test half), cost and latency per question; `mistral-embed` recall |
| Known limitations | Multi-page evidence; narrative "why" questions; questions without a company name; non-GAAP figures in earnings releases; LSA embeddings are weak semantically; benchmark-tuned glossary |
| Human oversight | Citations clickable to the PDF page; refusals with reasons; analysts verify before reuse |
| Monitoring | Refusal share, invalid citations, answer latency, tokens and estimated spend (Prometheus alerts) |
| Change control | Any change to prompts, glossary, routing or models re-runs `make eval` and, with a key, the `evals` workflow; results committed with date and model IDs |

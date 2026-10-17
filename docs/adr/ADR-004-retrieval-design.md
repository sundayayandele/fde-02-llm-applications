# ADR-004: Retrieval design

- **Status:** Accepted
- **Date:** 2026-10-15
- **Deciders:** Sunday Ayandele (owner)

## Context

Answers can only be as good as the passages retrieved. FinanceBench questions use analyst vocabulary ("capex", "net PPNE"), wrap the question in instructions ("Assume that you are a public equities analyst…"), and name a company and period. Filings use statement vocabulary ("Purchases of property, plant and equipment"). The corpus has 84 filings and 49,331 chunks.

## Options considered (page-level recall@5, right filing given; FinanceBench, 2026-10-15)

| Option | Recall@5 | Notes |
| --- | --- | --- |
| BM25 on the raw question | 0.320 | Vocabulary mismatch; instruction text adds noise |
| + query rewriting (strip boilerplate, finance glossary) | 0.587 | Largest single gain |
| + lexical rerank (coverage, fiscal year, statement cues) | 0.620 | Cheap, offline |
| Dense only (LSA), rewrite | 0.593 | Best recall@1 (0.400) |
| **Hybrid BM25 + LSA (RRF), rewrite, lexical rerank** | **0.653** | Best overall; MRR 0.517 |
| Whole corpus without routing (same pipeline) | 0.287 | Wrong-company passages crowd out the right ones |
| Routed by company and year | 0.600 | Realistic setting; 97% of questions routed to the right filing |
| Hybrid with `mistral-embed` | pending | Measured by the `evals` workflow with a key |

## Decision

Default to hybrid retrieval (BM25 + dense, RRF k = 60), query rewriting, filing routing and the lexical reranker. Use `mistral-embed` vectors when a key is available at indexing time, and LSA otherwise. The glossary and aliases are plain Python dictionaries that the customer's analysts can review.

## Consequences

- The glossary and company aliases were written while inspecting failures on FinanceBench itself. Measure on a held-out set of the customer's questions before quoting recall.
- Routing is the biggest lever on a multi-company corpus. When a question names no company, it falls back to whole-corpus search (a known failure case).
- The LLM reranker is available (`RERANKER=llm`) but costs one extra call per question. Evaluate it with the `evals` workflow before enabling it.

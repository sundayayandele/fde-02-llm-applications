# Capacity planning

## Measured (2026-10-15, 2 vCPU Xeon 2.1 GHz)

| Step | Measurement |
| --- | --- |
| Ingest 84 filings, 12,013 pages (44 OCR) | 364 s (about 33 pages/s; OCR pages dominate) |
| Fit LSA on 49,331 chunks | 54 s |
| Load the full index at start-up | about 6 s |
| Retrieval, hybrid + rerank | 85 ms p50 per question |
| Extractive answer end to end | 91 ms p50, 113 ms p95 |

## Estimates (not measured here)

- **LLM answers:** latency is dominated by the model: typically a few seconds for about 4–6k prompt tokens and a 150-token answer, plus one round trip per tool call. Measure with `make eval-llm`.
- **Throughput:** retrieval is CPU-bound at about 10 questions per second per core. Model calls are I/O-bound; one replica can hold many concurrent streams. Rate limits at the provider are the real ceiling.
- **Index growth:** about 4 chunks per page. Memory grows roughly linearly; beyond a few thousand filings, move dense vectors to a vector database (pgvector, OpenSearch, Qdrant) and BM25 to OpenSearch.

Replace the estimates with load-test numbers (`k6` or `hey` against `/api/v1/ask`) before a pilot.

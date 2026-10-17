# Learning guide: Phase 2, LLM applications (weeks 11–15) · Capstone 1

## Outcomes

By the end of this phase you can:

1. Call LLM APIs safely: providers, models by role, streaming, tool calling, costs, data residency.
2. Turn messy PDFs (including scanned pages and financial tables) into searchable, citable chunks.
3. Build retrieval from first principles (BM25), add dense vectors, fuse them, rewrite queries and route by metadata, and measure what each step buys.
4. Ground answers: numbered passages, citations you can verify, a refusal gate, exact arithmetic through tools, and an MCP server for other clients.
5. Evaluate a RAG system honestly (dev/test splits, recall@k, refusal rates, LLM judge, latency, cost) and present it to a customer.

## Weekly plan

| Week | Lab | Exercises |
| --- | --- | --- |
| 11 | [LLM APIs, prompts and citations](../../labs/week-11-llm-apis-and-citations/README.md) | `build_messages`, `parse_citations` |
| 12 | [Ingestion: PDFs, OCR and tables](../../labs/week-12-ingestion/README.md) | `table_to_markdown`, `chunk_text` |
| 13 | [Retrieval: BM25, dense and hybrid](../../labs/week-13-retrieval/README.md) | `bm25_idf`, `bm25_tf`, `rrf_fuse` |
| 14 | [Grounding: refusal, tools and MCP](../../labs/week-14-grounding-tools-mcp/README.md) | `should_refuse`, `compute_ratio` |
| 15 | [Evaluate, serve and present](../../labs/week-15-evaluate-and-serve/README.md) | `recall_at_k`, `numeric_match`, results table |

Budget about 12–14 hours per week. A Mistral API key is optional until week 14; everything runs offline before that. LLM costs for the whole phase are typically a few US dollars (assumed prices; you will measure your own).

## Exit check (Capstone 1)

```bash
make install && make test && make exercises && make e2e
make download && make ingest && make eval        # offline numbers
make eval-llm                                    # with MISTRAL_API_KEY
make up-docker                                   # open http://127.0.0.1:8000/
```

Plus: your results table, five failure cases with examples, a decision memo, and a short screen recording of the UI and of the MCP tools in an MCP client.

## Portfolio evidence a hiring manager will look for

- An ablation table showing what each retrieval step buys, not just one final number.
- Refusal measured on held-out data, with the threshold chosen on dev.
- Answers with page citations you can click, and cost per question.
- An MCP server other tools can use: it shows you build for the customer's ecosystem.

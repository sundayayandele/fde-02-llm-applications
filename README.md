# fde-02-llm-applications: document assistant over company filings

[![Open the starter in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/sundayayandele/fde-02-llm-applications-starter?quickstart=1)

Phase 2 (weeks 11–15) and **Capstone 1** of the **Forward Deployed ML Engineer: Zero-to-Hired** series. You build the most requested LLM system in enterprise work: an assistant that answers questions from a customer's own documents. It **cites the page every figure comes from**, and **says so when the documents don't contain the answer**.

**The system:** `filing-assistant`, a typed and tested Python package with a CLI, a streaming FastAPI service, a web UI and an MCP tool server, over public company filings (10-K, 10-Q, 8-K, earnings releases):

- **Ingestion:** PDF → pages (PDFium) with **OCR** for scanned pages (Tesseract). Financial statements are kept whole as **Markdown tables**. Chunks carry a contextual header (filing, page, section).
- **Retrieval:**
  - **BM25 written from scratch** plus dense vectors (`mistral-embed`, or an offline LSA embedder), combined with **reciprocal rank fusion**.
  - **Query rewriting** with a finance glossary ("capex" → "purchases of property, plant and equipment").
  - **Filing routing** by company and fiscal year.
  - A **reranker**: an offline lexical one, or a Mistral grader.
- **Guardrails (v1.1):** instruction-like sentences are quarantined and personal data masked at ingestion. Advice, personal-data, unknown-company and out-of-scope questions are declined. Answers are checked on the way out (ADR-008, measured by [fde-03](https://github.com/sundayayandele/fde-03-evaluation)).
- **Answers:** Mistral (or any provider in `config/providers.yaml`) answers only from numbered passages, cites them as `[n]`, and calls a **`financial_ratio` tool** for arithmetic. A **refusal gate** stops before any model call when the evidence is too weak. Without an API key, an **extractive baseline** answers offline.
- **Interfaces:**
  - `POST /api/v1/ask` (with tool calls) and `POST /api/v1/ask/stream` (server-sent events).
  - A web UI with clickable citations that open the PDF page.
  - An **MCP server** (`filing-assistant mcp`) exposing ratio, filing-lookup, search and page tools to Claude Desktop, Claude Code or any MCP client.

```mermaid
flowchart LR
  P[PDF filings] --> I[Ingest<br/>PDFium · OCR · tables → Markdown · chunks + headers]
  I --> X[(Index<br/>BM25 · dense vectors)]
  Q[Question] --> RW[Rewrite + route<br/>glossary · company · year]
  RW --> R[Hybrid retrieval<br/>BM25 + dense, RRF]
  X --> R
  R --> RR[Rerank]
  RR --> G{Refusal gate}
  G -- weak evidence --> REF[I can't answer that<br/>from the filings]
  G -- ok --> L[Mistral answer<br/>cites passages, calls ratio tool]
  L --> C[Grounded citations<br/>doc + page]
  T[MCP clients] --> M[MCP server<br/>ratio · lookup · search · page]
  X --> M
```

## Quick start

```bash
python3.12 -m venv .venv && source .venv/bin/activate
make install                     # also install Tesseract: apt install tesseract-ocr / brew install tesseract
make ingest-demo                 # fictional demo filings, offline, seconds
make run                         # UI on http://127.0.0.1:8000/
```

Real filings and the benchmark:

```bash
make download                    # FinanceBench: 150 questions + 84 PDFs, pinned commit
make ingest                      # ~6 minutes on 2 vCPU: 12,013 pages → 49,331 chunks
export MISTRAL_API_KEY=...       # optional: without it, answers are extractive
make ask Q="What is the FY2018 capital expenditure amount (in USD millions) for 3M?"
make eval                        # retrieval, refusal and extractive answers
make eval-llm                    # Mistral answers + LLM judge on the test half (costs cents)
```

## Results

Measured with the commands above on **FinanceBench (open-source sample)**: 150 questions over 84 filings, commit `cc39aeb4afdf`. Date 2026-10-15 (UTC). Raw reports are in [`evals/results/`](evals/results/).

<!-- >>> SOLUTION: week-15 results table -->
**Ingestion.** 84 filings, 12,013 pages (44 needed OCR), 49,331 chunks of which 7,133 are tables. 364 s on 2 vCPU (Xeon 2.1 GHz). LSA vectors: 54 s.

**Retrieval: page-level recall.** A question counts as found when a top-k passage is on a FinanceBench evidence page.

| Configuration | Scope | Recall@1 | Recall@5 | Recall@10 | MRR | p50 latency |
| --- | --- | --- | --- | --- | --- | --- |
| BM25 only | right filing given | 0.153 | 0.320 | 0.453 | 0.242 | 6 ms |
| + query rewriting | right filing given | 0.300 | 0.587 | 0.707 | 0.431 | 4 ms |
| + lexical rerank | right filing given | 0.360 | 0.620 | 0.753 | 0.482 | 11 ms |
| **Hybrid BM25 + LSA, rewrite, lexical rerank** | right filing given | **0.407** | **0.653** | **0.767** | **0.517** | 85 ms |
| Same | **routed by company and year** | 0.333 | 0.600 | 0.680 | 0.452 | 85 ms |
| Same | whole corpus, no routing | 0.100 | 0.287 | 0.340 | 0.182 | 83 ms |
| Hybrid BM25 + `mistral-embed` | routed | pending: `evals` workflow with `llm: true` | | | | |

**Refusal gate.** Answerable questions vs the same questions moved to FY1999, which no filing covers. Routed retrieval; coverage threshold 0.2, chosen on the dev half. Most refusals come from the period check (117 of 122); the rest from low term coverage.

| Half | False refusals (answerable) | Correct refusals (unanswerable) |
| --- | --- | --- |
| dev (79 answerable / 75 unanswerable) | 0.0% | 88.0% |
| **test (71 / 64)** | **0.0%** | **87.5%** |

**Answers.**

| Answerer | Numeric questions correct | Cites an evidence page | Judge accuracy (test half) | p50 / p95 latency | Cost per question |
| --- | --- | --- | --- | --- | --- |
| Extractive baseline (no LLM) | 9.4% (5 / 53) | 31.3% | not applicable | 91 / 113 ms | 0 |
| Mistral (`mistral-small-latest`) + ratio tool | pending | pending | pending | pending | pending |

Fill the Mistral row from the `evals` workflow (Actions → evals → Run workflow, `llm: true`, with a `MISTRAL_API_KEY` repository secret), or run `make eval-llm`. Record the model ID the API returns and the date.

**Honest caveats.** The glossary and the company aliases were written while looking at retrieval failures on this same benchmark, so expect lower recall on unseen filings. The refusal threshold was tuned on the dev half only. The extractive baseline cannot do arithmetic, which most FinanceBench metric questions need. That is exactly the gap the LLM and the ratio tool are there to close.

**v1.1.0 guardrails** (ADR-008), re-measured on 2026-10-16 with a v1.1.0 index, which masked personal data on 128 of the 12,013 pages and quarantined no sentences:

| Measure | v1.0.0 | v1.1.0 |
| --- | --- | --- |
| Routed hybrid + rewrite + lexical rerank, recall@5 | 0.600 | 0.593 |
| Same, right filing given, recall@5 | 0.653 | 0.667 |
| Refusal gate, test half: false / correct refusals | 0.0% / 87.5% | 0.0% / 87.5% |
| Extractive: numeric correct / cites an evidence page | 9.4% / 31.3% | 9.4% / 32.0% |
| fde-03 red team, all 26 cases / critical categories | 12 / 26, 0% | 24 / 26, 100% |
| fde-03 refusal golden set (30 unanswerable questions) | 16.7% declined | 80.0% declined |

The safety evidence and the release decision are in fde-03's [release-readiness memo](https://github.com/sundayayandele/fde-03-evaluation/blob/main/docs/RELEASE-READINESS.md).

**Known failure cases** (see `misses` in the retrieval report):
1. Questions that name no company ("Was there any drop in Cash & Cash equivalents…").
2. Conceptual questions whose evidence is narrative ("What drove operating margin change…").
3. Evidence spread over two or more pages.
4. Quarterly questions routed to both the 10-Q and the 10-K.
5. Earnings-release metrics that do not appear in the statement tables (adjusted, non-GAAP).
<!-- <<< SOLUTION -->

## Run it everywhere

| Path | Command | What runs |
| --- | --- | --- |
| Local Python | `make install && make e2e` | Demo index, API, smoke checks (extractive mode) |
| Docker Desktop | `make up-docker` | Image with a baked index: 6 FinanceBench filings + demo (`CORPUS=sample`) |
| Podman Desktop | `make up-podman` | Same image as a pod; Mistral key from an optional secret |
| Rancher Desktop | `make up-rancher` | Same image on Rancher's moby engine |
| Local Kubernetes | `make k8s-docker`, `make k8s-rancher`, `make k8s-kind` | Deployment, HPA, PDB, NetworkPolicy |
| OpenShift / Helm | `oc apply -k deploy/openshift` · `helm install` | Route with edge TLS; key from a Secret |
| AWS / Azure / GCP | `make tf-aws-plan` (and `azure`, `gcp`) | Fargate, Container Apps, Cloud Run; key in each cloud's secret store |

Image corpora: `docker build --build-arg CORPUS=demo|sample|full`. Set `MISTRAL_API_KEY` at run time for LLM answers. Step by step: [desktop labs](docs/learning/DESKTOP-LABS.md), [cloud labs](docs/learning/CLOUD-LABS.md), [deployment](docs/DEPLOYMENT.md).

## Use it from Claude Desktop or any MCP client

```json
{"mcpServers": {"filing-assistant": {
  "command": "/path/to/.venv/bin/filing-assistant",
  "args": ["--index-dir", "/path/to/fde-02-llm-applications/index", "mcp"]}}}
```

Tools (all read-only): `financial_ratio`, `list_ratios`, `filing_lookup`, `search_filings`, `get_page`. HTTP transport: `filing-assistant mcp --transport streamable-http`.

## API

| Endpoint | Returns |
| --- | --- |
| `GET /` | Web UI: streamed answer, clickable `[n]` citations, sources with "open PDF page" links |
| `POST /api/v1/ask` `{question, docs?}` | `answer`, `citations` (doc, page), `refused`, `refusal_reason`, `hits`, `tool_calls`, `timings_ms`, `usage`, `cost_usd` |
| `POST /api/v1/ask/stream` | Server-sent events: `hits`, `token`…, `done` (citations, usage, cost) |
| `POST /api/v1/search` `{query, k, docs?}` | Passages with doc, page and scores |
| `GET /api/v1/filings?company&year&type` | Indexed filings |
| `GET /api/v1/filings/{doc}/pages/{n}` · `/pdf` | Extracted page text · the PDF |
| `POST /api/v1/tools/ratio` | Exact ratio calculation |
| `GET /health/*`, `GET /metrics/` | Health; questions, refusals, answer time, tokens, estimated cost, invalid citations |

## Learning path

| Week | Lab | You build |
| --- | --- | --- |
| 11 | [LLM APIs, prompts and citations](labs/week-11-llm-apis-and-citations/README.md) | `build_messages`, `parse_citations` |
| 12 | [Ingestion: PDFs, OCR and tables](labs/week-12-ingestion/README.md) | `table_to_markdown`, `chunk_text` |
| 13 | [Retrieval: BM25, dense and hybrid](labs/week-13-retrieval/README.md) | `bm25_idf`, `bm25_tf`, `rrf_fuse` |
| 14 | [Grounding: refusal, tools and MCP](labs/week-14-grounding-tools-mcp/README.md) | `should_refuse`, `compute_ratio` |
| 15 | [Evaluate, serve and present](labs/week-15-evaluate-and-serve/README.md) | `recall_at_k`, `numeric_match`, results table |

**Capstone 1 exit check:** from a fresh clone, `make test`, `make exercises` and `make e2e` pass. The FinanceBench index builds. Your results table has retrieval recall, refusal rates and answer accuracy, with latency and cost per question. The assistant runs in a container on one desktop engine and is usable from an MCP client. Your write-up names five failure cases and what you would do next.

## Repository map

```text
app/main.py, app/static/   API (JSON + SSE) and web UI
src/filing_assistant/      ingest, index, bm25, embed, retrieve, query, router, rerank, answer,
                           tools, pipeline, evaluate, financebench, demo, llm, mcp_server, cli
tests/                     unit, pipeline, MCP, API and CLI tests; e2e/smoke.yaml
evals/results/             committed FinanceBench reports behind the results table
labs/                      weeks 11–15
docs/                      architecture, ADRs, customer brief, system card, evaluation, datasets, security, cost
deploy/ · terraform/ · monitoring/
```

## Reference and starter

[`fde-02-llm-applications`](https://github.com/sundayayandele/fde-02-llm-applications) is the **reference** repo: complete code and measured results. [`fde-02-llm-applications-starter`](https://github.com/sundayayandele/fde-02-llm-applications-starter) is generated from it with `make starter`: each exercise becomes a `NotImplementedError("TODO ...")` stub, exercise tests carry `@pytest.mark.exercise` (`make exercises`), and the results table is blank for your numbers.

## Licence

Code: [MIT](LICENSE). Written content: [CC BY-SA 4.0](LICENSE-CONTENT.md). FinanceBench is downloaded at run time and not redistributed. Its repository has no licence file; the Hugging Face card lists CC BY-NC 4.0 (verify), so use it for learning and evaluation, not commercially. The filings themselves are public SEC documents. "Northwind Retail" in the demo corpus is fictional. See [DATASETS](docs/datasets/DATASETS.md).

Part of [fde-zero-to-hired](https://github.com/sundayayandele/fde-zero-to-hired) by Sunday Ayandele.

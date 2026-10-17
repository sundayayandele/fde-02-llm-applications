# Infrastructure

One container image with the API, UI, CLI and MCP server, and an index baked in at build time (`CORPUS=demo|sample|full`).

| Target | Runtime | Size | Mistral key from |
| --- | --- | --- | --- |
| Local Python | `make run` | — | `.env` |
| Docker / Rancher Desktop | Compose | 1 CPU, 1.5 GiB | shell / `.env` |
| Podman Desktop | Pod | 1 CPU, 1.5 GiB | optional Podman secret |
| Desktop Kubernetes | Deployment (1 replica), HPA, PDB, NetworkPolicy | requests 250m/768Mi, limits 1/1.5Gi | optional Secret |
| Managed Kubernetes / OpenShift / Helm | Deployment (2 replicas), Ingress or Route | same | Secret |
| AWS | ECS Fargate | 0.5 vCPU / 2 GB | Secrets Manager |
| Azure | Container Apps | 1 vCPU / 2 GiB | Key Vault + managed identity |
| GCP | Cloud Run | 1 vCPU / 2 GiB | Secret Manager |

Memory: the `sample` index (6 filings + demo) needs a few hundred MB. The `full` index (84 filings) loads about 1 GB (chunks, BM25 postings, LSA arrays). Raise limits to 2–3 GiB for `CORPUS=full`.

Configuration: `RETRIEVAL_MODE`, `EMBEDDER`, `RERANKER`, `ROUTE`, `MIN_COVERAGE`, `ANSWER_MODE`, `LLM_ROLE`, `USE_TOOLS` (see `.env.example`).

Monitoring: alerts `RefusalRateHigh`, `InvalidCitations`, `LLMSpendHigh` plus the template's service alerts. Grafana shows answered vs refused, answer time, tokens and estimated spend.

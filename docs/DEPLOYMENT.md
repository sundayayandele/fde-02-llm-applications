# Deployment

Every path runs the same image: API, UI, CLI and MCP server, with an index in `/app/index`. Set `MISTRAL_API_KEY` for LLM answers; without it the service answers in extractive mode.

| Path | Command | Details |
| --- | --- | --- |
| Local Python | `make ingest-demo && make run` | Or `make download && make ingest` for FinanceBench |
| Docker Desktop | `make up-docker`, `make k8s-docker` | [Desktop labs](learning/DESKTOP-LABS.md#1a-docker-desktop) |
| Podman Desktop | `make up-podman`, `make k8s-kind` | [Desktop labs](learning/DESKTOP-LABS.md#1b-podman-desktop) |
| Rancher Desktop | `make up-rancher`, `make k8s-rancher` | [Desktop labs](learning/DESKTOP-LABS.md#1c-rancher-desktop) |
| Managed Kubernetes | `kubectl apply -k deploy/kubernetes/overlays/cloud` | Secret `fde-02-llm-applications-secrets` with `MISTRAL_API_KEY` |
| Helm | `helm upgrade --install assistant deploy/helm/fde-02-llm-applications` | `--set route.enabled=true` on OpenShift |
| OpenShift | `oc apply -k deploy/openshift` | Route with edge TLS |
| AWS / Azure / GCP | `make tf-<cloud>-plan`, then the stack README | [Cloud labs](learning/CLOUD-LABS.md) |
| MCP (desktop clients) | `filing-assistant mcp` | See README for the Claude Desktop config |

## Build options

| Build argument | Default | Effect |
| --- | --- | --- |
| `CORPUS` | `sample` | `demo` (offline, 2 fictional filings), `sample` (6 FinanceBench filings + demo), `full` (84 + demo; raise memory to 3 GiB) |
| `SAMPLE_DOCS` | 6 filings | Which FinanceBench filings `sample` includes |

## Release

1. Update `CHANGELOG.md`; bump versions (`pyproject.toml`, `__init__.py`, `Chart.yaml`, cloud overlay tag, Terraform `image_tag`).
2. `make eval`, and with a key the `evals` workflow; update the README results table and ADRs if the ranking changed.
3. Tag `vX.Y.Z`; `publish-starter` regenerates the starter.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `ask` returns 503 | No index: `/health/ready` → `index: false`; rebuild the image or run `filing-assistant ingest` |
| Answers are extractive | `/health/ready` → `answer_mode`; set `MISTRAL_API_KEY` |
| Stream ends with `event: error` | Provider error (key, quota, network). Check egress and the key; `/ask` returns the HTTP error |
| Many refusals (`RefusalRateHigh`) | Filings missing for the companies or periods asked; check `refusal_reason` in responses |
| `InvalidCitations` alert | The model cited passages it did not get: check for prompt changes or a provider model update |
| `LLMSpendHigh` | Traffic spike or loop; check `questions_total` and tokens per question |
| Slow answers | `answer_seconds` vs retrieval time in `timings_ms`; usually the model. Try `LLM_ROLE=default` and fewer passages |

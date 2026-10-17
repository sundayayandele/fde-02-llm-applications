# Security

## Reporting

Open a private security advisory on the GitHub repository. Do not file public issues for vulnerabilities.

## Controls in this repo

| Area | Control |
| --- | --- |
| Secrets | `MISTRAL_API_KEY` comes from the environment, Kubernetes Secrets, Podman secrets, Secrets Manager, Key Vault or Secret Manager. Without it the service still works, offline (extractive mode). |
| Data residency | The provider client blocks regulated data to providers with `regulated_data_allowed: false`. Filings are public; internal documents must stay on Mistral (EU) or a self-hosted model. |
| Logging | Questions, passages and answers are not logged. Metrics carry counts, timings, tokens and estimated cost only. |
| Prompt injection | Passages are presented as numbered data under a system prompt that restricts the model to them. The model's only tool is a pure calculator; MCP tools are read-only (annotated `readOnlyHint`). Citations to passages not sent are dropped and counted. The UI escapes all model output. |
| Index integrity | Source PDFs are pinned to a Git commit and the question file is checked by SHA-256. The index stores plain JSON and NumPy arrays (no pickles). |
| Input limits | Questions 3–2,000 characters; search `k` ≤ 30; file names in page and PDF routes must be indexed filings, so there is no path traversal. |
| Least privilege | UID 10001, no capabilities, read-only root filesystem, seccomp RuntimeDefault, restricted Pod Security Standard. |
| Supply chain | `security` workflow: pip-audit, gitleaks, Trivy. |

See [THREAT-MODEL](THREAT-MODEL.md).

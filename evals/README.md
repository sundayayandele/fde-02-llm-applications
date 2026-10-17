# Evals

| What | Command | Output |
| --- | --- | --- |
| Retrieval (all configurations, three scopes) | `filing-assistant eval-retrieval` | `evals/results/financebench-retrieval-<date>.json` |
| Refusal gate | `filing-assistant eval-refusal --split dev` then `--split test` | `financebench-refusal-routed-<split>-<date>.json` |
| Answers, offline | `filing-assistant eval-answers --answer-mode extractive` | `financebench-answers-extractive-routed-all-<date>.json` |
| Answers, Mistral + judge | `make eval-llm` | `financebench-answers-llm-routed-test-<date>.json` |
| On GitHub | Actions → evals (`llm: true` needs the `MISTRAL_API_KEY` secret) | `financebench-results` artefact and a job summary |

Protocol and caveats: [EVALUATION](../docs/mlops/EVALUATION.md). Your own corpus: pass `--questions questions.json` (format in `filing_assistant/demo.py`).

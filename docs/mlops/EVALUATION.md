# Evaluation

## Benchmark

FinanceBench open-source sample: 150 questions with gold answers and evidence pages over 84 filings. Question types: 50 metrics-generated (mostly numeric), 50 domain-relevant, 50 novel. Split deterministically into **dev** (79) and **test** (71) halves by hashing the question ID. Thresholds are tuned on dev only.

## What is measured

| Stage | Metric | How |
| --- | --- | --- |
| Retrieval | Page-level recall@1/3/5/10, MRR, latency | A hit is a top-k passage from the evidence filing and an evidence page. Three scopes: right filing given, routed, whole corpus |
| Refusal | False-refusal rate (answerable) and correct-refusal rate | Unanswerable variants: every year in the question replaced by 1999 |
| Answers | Numeric match (first number within 1%, allowing millions/billions scaling); LLM-judge verdict (CORRECT / INCORRECT / REFUSED); share of answers citing an evidence page | Judge: Mistral Large with a fixed rubric, JSON output |
| Cost and speed | p50/p95 end-to-end latency; tokens; USD per question at assumed prices | From API usage fields |

## Commands

```bash
make eval                         # offline: retrieval, refusal (dev, test), extractive answers
make eval-llm                     # Mistral answers + judge on the test half
filing-assistant eval-answers --answer-mode llm --judge --split test --scope doc   # oracle filing
```

Reports land in `evals/results/` with provenance (date, package version, index totals, configuration, machine).

## Reading the numbers

- 150 questions is small: ±4 points of recall is noise. Compare configurations on the same report.
- The LLM judge is an estimate until calibrated against analysts' labels (fde-03). Spot-check 20 verdicts by hand before quoting accuracy.
- Retrieval recall caps answer accuracy: an answer cannot be grounded on a page that was never retrieved.

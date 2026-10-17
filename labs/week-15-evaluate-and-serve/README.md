# Week 15: Evaluate, serve and present (Capstone 1)

**Goal:** measure the whole system honestly, run it as a service anywhere, and present it like a forward-deployed engineer.

## Brief

Friday is the pilot decision. The head of research wants three numbers: how often the assistant finds the evidence, how often it refuses when it should and when it shouldn't, and how often its answers are right. Then: what it costs, and what it gets wrong.

## Concepts

Page-level recall@k; numeric answer matching; LLM-as-judge (rubrics, JSON verdicts, and why judges need calibrating); latency percentiles; cost per question; failure analysis; streaming UIs; presenting results with caveats.

## Steps

1. Implement `recall_at_k(hits, doc, pages, k)` and `numeric_match(prediction, gold, rel_tol)` in `evaluate.py`.
2. `make exercises` (all green), `make e2e`, then `make eval`.
3. With a key: `make eval-llm` (or run the GitHub `evals` workflow with `llm: true`). Note judge accuracy by question type, cost per question, p95 latency.
4. Hand-check 10 judge verdicts against the gold answers. How many do you agree with?
5. Fill the README results table (with the date, commit, model IDs) and write five failure cases with an example each.
6. `make up-docker`, open the UI, ask one answerable and one unanswerable question, and record a 2-minute demo.
7. Update `docs/customer/DECISION-MEMO.md` with your numbers.

## Check

```bash
make exercises && make e2e && make eval
```

## Evidence

Results table, failure cases, decision memo, demo recording, and the MCP screenshot from week 14: that is Capstone 1.

## Stretch

Swap in another corpus (CUAD contracts or GovReport, see DATASETS) with `filing-assistant ingest --pdfs <folder>`, write 20 questions with gold answers and evidence pages in the demo JSON format, and run `eval-retrieval --questions <file>`.

## Capstone 1 exit check

From a fresh clone: `make test`, `make exercises`, `make e2e` pass; FinanceBench index builds; results table with retrieval, refusal, answer accuracy, latency and cost; container running on a desktop engine; MCP tools usable from a client; five failure cases written up.

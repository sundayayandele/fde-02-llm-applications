# ADR-005: Refuse before the model when evidence is weak

- **Status:** Accepted
- **Date:** 2026-10-15
- **Deciders:** Sunday Ayandele (owner)

## Context

In finance, a confident wrong number is worse than "I don't know". Models given irrelevant passages often answer anyway. Every model call also costs money and time.

## Options considered

| Option | Pros | Cons |
| --- | --- | --- |
| Rely on the prompt rule only ("say you can't answer") | Simple | Models still answer from near-miss passages |
| Retrieval-score threshold | Cheap | BM25 and RRF scores are not comparable across queries |
| **Deterministic gate: term coverage + fiscal-period check, then the prompt rule** | Explainable, free, tunable on data | Checks words and years, not meaning |
| LLM verifier pass | Catches subtle mismatches | Extra call per question |

## Decision

`should_refuse` refuses when there are no passages, when no passage covers at least 20% of the question's content terms, or when the question names fiscal years and none appears in the passages. The threshold was chosen on the FinanceBench dev half: false refusals 1.3% → 0.0% after a later fix, correct refusals 88.0%. On the test half: **0.0% false refusals, 87.5% correct refusals** on questions moved to FY1999. The prompt keeps its own refusal sentence as a second line of defence.

## Consequences

- Refusals carry a reason (`no_evidence`, `low_coverage`, `period_not_found`, `model_refused`) in the API and metrics.
- The 12.5% of unanswerable variants that pass the gate are passages that happen to mention 1999 (e.g. "since 1999"). The model must catch those; `fde-03` measures how often it does.
- Alert when the refusal share rises (`RefusalRateHigh`): usually missing filings or questions about a new period.

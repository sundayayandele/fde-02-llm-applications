# Decision memo: filing assistant pilot

**To:** Head of Research, Harbour Capital (fictional) · **From:** Forward-deployed engineer · **Date:** 2026-10-15

## Recommendation

Run a four-week pilot with five analysts on the filings of the 84 companies in the current index, in **cite-and-verify** mode. Analysts use the answer and must click at least one citation before reusing a figure. Retrieval and refusal are ready. Answer quality goes live only after the first measured Mistral run meets the bar agreed below.

## Why

- **It finds the evidence.** In the realistic setting (question routed to the company's filings), the right page is in the top five passages for 60% of FinanceBench questions, and in the top ten for 68%. Query rewriting with a finance glossary doubled recall over plain keyword search.
- **It refuses rather than guesses.** On held-out questions about a year no filing covers, it refused 87.5% before calling any model, and it refused none of the answerable questions.
- **Every figure is traceable.** Answers cite numbered passages; citations to anything the model was not given are dropped and alerted on. The UI opens the PDF at the cited page.
- **Arithmetic is exact.** Ratios and growth rates go through a calculator tool, not the model.
- **Cost is small.** Estimated well under one US cent per question with Mistral Small (assumed list prices; confirmed by the first measured run).

## Options considered

| Option | Verdict |
| --- | --- |
| Generic chatbot with document upload | Rejected: no page citations, no refusal behaviour, no evaluation |
| Search engine over filings | Useful but leaves the reading and arithmetic to the analyst |
| **This assistant (retrieval + refusal gate + cited LLM answers + tools)** | **Recommended for pilot** |
| Fine-tuned model | Premature: retrieval, not knowledge, is the bottleneck (fde-04 revisits) |

## Risks

| Risk | Mitigation |
| --- | --- |
| Wrong figure from a near-miss passage | Cite-and-verify workflow; refusal gate; judge-measured accuracy before go-live |
| Benchmark tuned on itself | Glossary and aliases reviewed by analysts; re-measure on Harbour's own question set |
| Questions without a company name | UI filing selector; router falls back to whole-corpus search |
| Prompt injection inside a document | Passages are treated as data; tools are read-only; red-team suite in fde-03 |

## Decision needed

Approve the pilot and a USD 50 API budget for evaluation and pilot traffic.

# Week 11: LLM APIs, prompts and citations

**Goal:** call an LLM through a provider-agnostic client and make it answer only from passages it can cite.

## Brief

Harbour Capital stopped a chatbot pilot after it invented a capex figure. Your first deliverable is the contract between your code and the model: what it is given, what it may say, and how every claim points back to a passage.

## Concepts

Chat completions; system vs user messages; temperature; tokens and pricing; streaming (server-sent events); tool calling; provider abstraction and data residency (`config/providers.yaml`); grounding and citations.

## Steps

1. Read `src/filing_assistant/llm.py`: `complete`, `stream`, `embed`, `cost_usd`. Run `pytest tests/test_llm_client.py`: it uses a mock transport, so there is no key and no cost.
2. Read `SYSTEM_PROMPT` in `answer.py`. Which rule stops the model inventing figures? Which one makes refusals detectable?
3. Implement `build_messages(question, hits)`: system message, then a user message of numbered context passages (`format_context`) followed by the question.
4. Implement `parse_citations(text)`: passage numbers from `[2]`, `[1][3]`, `[1, 4]`, in first-seen order without duplicates.
5. `pytest tests/test_answer_rerank.py -m exercise -k "messages or citations"`.
6. With a key (optional): `export MISTRAL_API_KEY=...`, `make ingest-demo`, then `make ask Q="What was Northwind's FY2023 capital expenditure?"`. Read the citations and the cost line.

## Check

```bash
pytest tests/test_answer_rerank.py -m exercise -k "messages or citations" && make lint
```

## Evidence

One answer with its citations and token cost (or the extractive answer, if you have no key), and a sentence on what `ground_citations` protects against.

## Stretch

Point the client at a second provider in `providers.yaml` (for example DeepSeek or Qwen for public filings). Ask the same three questions, and compare answers, citation behaviour and cost. Why must regulated data never take that path?

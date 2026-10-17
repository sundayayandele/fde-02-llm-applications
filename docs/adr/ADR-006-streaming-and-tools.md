# ADR-006: Tools in `/ask`, plain streaming in `/ask/stream`

- **Status:** Accepted
- **Date:** 2026-10-15
- **Deciders:** Sunday Ayandele (owner)

## Context

Users want to see answers appear quickly (streaming). Arithmetic should be done by a tool, not by the model. Streamed tool calls arrive as partial JSON deltas, which complicates the client and the error handling.

## Options considered

| Option | Pros | Cons |
| --- | --- | --- |
| Tools everywhere, parse streamed tool-call deltas | One behaviour | Complex; tool rounds delay the first token anyway |
| Tool rounds first (non-streamed), then stream the final answer | Streams the visible part | Extra call even when no tool is needed |
| **`/ask` with tools; `/ask/stream` without tools** | Simple and predictable; UI streams; API clients get exact maths | Two behaviours to document |

## Decision

The UI uses `/ask/stream` for responsiveness; integrations and the evaluation use `/ask`, which runs up to three tool rounds. Both share retrieval, the refusal gate and citation grounding.

## Consequences

- Streamed answers may contain model arithmetic. The UI shows the passages, so a reader can check them, and computational questions should go through `/ask`.
- Revisit when the provider's streamed tool-call support is stable across all providers in `providers.yaml`.

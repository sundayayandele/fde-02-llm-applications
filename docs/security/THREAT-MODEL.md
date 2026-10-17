# Threat model

LLM-specific threats follow the OWASP Top 10 for LLM Applications categories; classic threats use STRIDE.

| Threat | Category | Mitigation | Residual |
| --- | --- | --- | --- |
| Instructions hidden in a filing ("ignore previous instructions…") reach the model | Prompt injection (indirect) | v1.1: instruction-like sentences quarantined at ingestion (recorded in the manifest); passages framed as data in the prompt; answers carrying an instruction withheld; no side-effecting tools; output escaped in UI (ADR-008) | Medium: paraphrased instructions; fde-03 red team 4 of 4 indirect cases pass on v1.1.0 (0 of 4 on v1.0.0) |
| Personal data in a document is repeated in an answer | Information disclosure | v1.1: SSN, email, phone, Luhn-valid cards and role-word names masked at ingestion and on output (ADR-008) | Names without a role word; the original PDF is still served by `/pdf`. fde-03: 5 of 5 PII cases pass on v1.1.0 (0 of 5 on v1.0.0) |
| Investment advice, personal-data requests, unknown companies | Reputational, regulatory | v1.1: scope check before answering (`SCOPE_GUARD=finance`) | Paraphrased requests; false premises still answered |
| User asks the assistant to reveal its prompt or invent figures | Prompt injection (direct) | Grounded-answer rule; refusal sentence; citation grounding | Low impact: prompt contains no secrets |
| Answer with a fabricated figure | Misinformation | Refusal gate, page citations, invalid-citation alert, exact ratio tool, judge-measured accuracy | Medium until measured with the LLM |
| Model calls tools with harmful arguments | Excessive agency | Only a pure calculator; three tool rounds at most; MCP tools read-only | Low |
| API key leaked | Sensitive information disclosure | Secret stores; never logged; not in images | Low |
| Internal notes sent to a non-EU provider | Sensitive information disclosure | `regulated_data_allowed` guard in the client | Low when callers flag regulated data |
| Poisoned or altered source PDFs | Data poisoning | Pinned commit + checksums; ingestion from known sources only | Low for FinanceBench; customer sources need their own controls |
| Cost blow-up from heavy use | Unbounded consumption | Input limits, refusal gate (no model call), `LLMSpendHigh` alert, HPA limits | Medium without rate limiting: add at the gateway |
| Unauthenticated access (labs) | Spoofing | Lab only; put behind SSO or an API gateway for real use | Medium in labs |
| Container escape | Elevation of privilege | Non-root, no capabilities, read-only FS, seccomp | Low |

## Accepted lab trade-offs

| Trade-off | Production fix |
| --- | --- |
| No authentication on API and MCP HTTP transport | SSO at the ingress; MCP over stdio or behind auth |
| Egress open (Mistral API) | Egress policy to the provider's hostnames only |
| AWS task with public IP, no load balancer | ALB with TLS, private subnets |

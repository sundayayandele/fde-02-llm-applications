"""The assistant: retrieve → rerank → refusal gate → answer (LLM with tools, or extractive).

Two entry points: `ask()` returns a complete answer (and may call tools); `ask_stream()`
yields events for a streaming UI: "hits", then "token" deltas, then "done" with citations.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from dataclasses import dataclass, field

from filing_assistant.answer import (
    REFUSAL,
    build_messages,
    extractive_answer,
    ground_citations,
    is_refusal,
    should_refuse,
)
from filing_assistant.guardrails import mask_pii, quarantine, scope_check
from filing_assistant.index import Index
from filing_assistant.rerank import get_reranker
from filing_assistant.retrieve import Hit, Retriever
from filing_assistant.tools import TOOL_SPECS, run_tool


@dataclass
class AssistantConfig:
    mode: str = "hybrid"               # bm25 | dense | hybrid
    embedder: str | None = None        # lsa | mistral (dense vectors in the index)
    reranker: str = "lexical"          # none | lexical | llm
    candidates: int = 30               # retrieved before reranking
    context: int = 6                   # passages sent to the model
    answer_mode: str = "auto"          # auto | llm | extractive
    provider: str | None = None        # LLM provider name (providers.yaml); None = default
    role: str = "default"              # model role (default | strong)
    use_tools: bool = True
    route: bool = True                 # resolve company/period to filings before searching
    min_coverage: float = 0.2
    scope_guard: str = "finance"       # finance | off
    mask_output_pii: bool = True
    max_tool_rounds: int = 3
    temperature: float = 0.0


@dataclass
class Answer:
    question: str
    answer: str
    refused: bool
    refusal_reason: str | None
    citations: list[dict]
    invalid_citations: list[int]
    mode: str
    model: str | None
    hits: list[dict]
    timings_ms: dict[str, float]
    usage: dict = field(default_factory=dict)
    cost_usd: float | None = None
    tool_calls: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _hit_dict(ref: int, h: Hit) -> dict:
    return {"ref": ref, "doc": h.chunk.doc, "page": h.chunk.page, "kind": h.chunk.kind,
            "title": h.chunk.title, "score": round(h.score, 5),
            "rerank_score": round(h.rerank_score, 4) if h.rerank_score is not None else None,
            "ranks": h.ranks, "preview": h.chunk.text[:300]}


class Assistant:
    def __init__(self, index: Index, config: AssistantConfig | None = None, client=None) -> None:
        self.index = index
        self.config = config or AssistantConfig()
        if self.config.mode != "bm25" and not index.dense:
            self.config.mode = "bm25"
        self.retriever = Retriever(index, mode=self.config.mode, embedder=self.config.embedder,
                                   candidates=self.config.candidates)
        self.reranker = get_reranker(self.config.reranker)
        self._client = client
        self._known_keys: set[str] | None = None

    # -- guardrails (ADR-008) -------------------------------------------------------------
    @property
    def known_keys(self) -> set[str]:
        """Normalised names of every indexed company (full name, prefix, aliases)."""
        if self._known_keys is None:
            from filing_assistant.router import company_keys
            keys: set[str] = set()
            for doc, info in self.index.doc_info.items():
                keys |= company_keys(info.get("company", doc.split("_")[0]), doc)
            self._known_keys = keys
        return self._known_keys

    def scope_reason(self, question: str) -> str | None:
        if self.config.scope_guard == "off":
            return None
        return scope_check(question, self.known_keys)

    def guard_output(self, text: str) -> tuple[str, str | None]:
        """Answer text with personal data masked; a reason when it carries an instruction
        from a document (the model followed an injection), in which case it is withheld."""
        if quarantine(text)[1]:
            return REFUSAL, "unsafe_output"
        if self.config.mask_output_pii:
            text = mask_pii(text)[0]
        return text, None

    # -- plumbing -------------------------------------------------------------------------
    def answer_mode(self) -> str:
        if self.config.answer_mode != "auto":
            return self.config.answer_mode
        if self._client is not None:
            return "llm"
        from filing_assistant.llm import LLMConfigError, client_for
        try:
            self._client = client_for(self.config.provider)
            return "llm"
        except LLMConfigError:
            return "extractive"

    @property
    def client(self):
        if self._client is None:
            from filing_assistant.llm import client_for
            self._client = client_for(self.config.provider)
        return self._client

    def route(self, question: str) -> list[str] | None:
        if not self.config.route:
            return None
        from filing_assistant.router import resolve_docs
        return resolve_docs(question, self.index.doc_info, self.index.docs) or None

    def retrieve(self, question: str, docs: list[str] | None = None) -> tuple[list[Hit], dict]:
        t0 = time.perf_counter()
        if docs is None:
            docs = self.route(question)
        hits = self.retriever.search(question, k=self.config.candidates, docs=docs)
        t1 = time.perf_counter()
        hits = self.reranker.rerank(question, hits)[: self.config.context]
        t2 = time.perf_counter()
        return hits, {"retrieve": round((t1 - t0) * 1000, 2), "rerank": round((t2 - t1) * 1000, 2)}

    def _cost(self, model: str | None, usage: dict) -> float | None:
        if not model or not usage:
            return None
        provider = self.client.provider
        return provider.cost_usd(model, usage.get("prompt_tokens", 0),
                                 usage.get("completion_tokens", 0))

    # -- non-streaming --------------------------------------------------------------------
    def ask(self, question: str, docs: list[str] | None = None) -> Answer:
        t_start = time.perf_counter()
        hits, timings = self.retrieve(question, docs)
        mode = self.answer_mode()
        reason = self.scope_reason(question) or should_refuse(question, hits,
                                                              self.config.min_coverage)
        model, usage, tool_log = None, {}, []
        t0 = time.perf_counter()
        if reason:
            text = REFUSAL
        elif mode == "extractive":
            text, _ = extractive_answer(question, hits)
        else:
            text, model, usage, tool_log = self._llm_answer(question, hits)
        if not reason:
            text, reason = self.guard_output(text)
        timings["generate"] = round((time.perf_counter() - t0) * 1000, 2)
        timings["total"] = round((time.perf_counter() - t_start) * 1000, 2)
        refused = reason is not None or is_refusal(text)
        citations, invalid = ground_citations(text, hits)
        return Answer(question, text, refused, reason or ("model_refused" if refused else None),
                      [c.to_dict() for c in citations], invalid, mode, model,
                      [_hit_dict(i, h) for i, h in enumerate(hits, 1)], timings, usage,
                      self._cost(model, usage) if mode == "llm" else None, tool_log)

    def _llm_answer(self, question: str, hits: list[Hit]) -> tuple[str, str, dict, list[dict]]:
        messages: list[dict] = build_messages(question, hits)
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        tool_log: list[dict] = []
        params: dict = {"temperature": self.config.temperature}
        if self.config.use_tools:
            params |= {"tools": TOOL_SPECS, "tool_choice": "auto"}
        out: dict = {}
        for _ in range(self.config.max_tool_rounds + 1):
            out = self.client.complete(messages, role=self.config.role, **params)
            for key in usage:
                usage[key] += (out["usage"] or {}).get(key, 0)
            if not out["tool_calls"]:
                break
            messages.append({"role": "assistant", "content": out["content"] or "",
                             "tool_calls": out["tool_calls"]})
            for call in out["tool_calls"]:
                fn = call.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                result = run_tool(fn.get("name", ""), args)
                tool_log.append({"name": fn.get("name"), "arguments": args, "result": result})
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                 "name": fn.get("name", ""), "content": json.dumps(result)})
            if len(tool_log) >= self.config.max_tool_rounds:
                params = {"temperature": self.config.temperature}   # force a final answer
        return (out.get("content") or REFUSAL), out.get("model"), usage, tool_log

    # -- streaming ------------------------------------------------------------------------
    def ask_stream(self, question: str, docs: list[str] | None = None) -> Iterator[dict]:
        """Events: {"event": "hits", ...}, {"event": "token", "text"}, {"event": "done", ...}.
        Streaming answers do not call tools (see ADR-006)."""
        t_start = time.perf_counter()
        hits, timings = self.retrieve(question, docs)
        mode = self.answer_mode()
        yield {"event": "hits", "mode": mode,
               "hits": [_hit_dict(i, h) for i, h in enumerate(hits, 1)]}
        reason = self.scope_reason(question) or should_refuse(question, hits,
                                                              self.config.min_coverage)
        model, usage, parts = None, {}, []
        t0 = time.perf_counter()
        if reason or mode == "extractive":
            text = REFUSAL if reason else extractive_answer(question, hits)[0]
            if not reason:
                text, reason = self.guard_output(text)
            parts.append(text)
            yield {"event": "token", "text": text}
        else:
            model = self.client.provider.model_for(self.config.role)
            for event in self.client.stream(build_messages(question, hits), role=self.config.role,
                                            temperature=self.config.temperature):
                if "delta" in event:
                    parts.append(event["delta"])
                    yield {"event": "token", "text": event["delta"]}
                else:
                    usage = event.get("usage") or {}
        text = "".join(parts)
        if model and not reason:
            # Tokens already went out; the final event carries the guarded text to replace them.
            guarded, reason = self.guard_output(text)
            if guarded != text:
                text = guarded
                yield {"event": "replace", "text": text}
        timings["generate"] = round((time.perf_counter() - t0) * 1000, 2)
        timings["total"] = round((time.perf_counter() - t_start) * 1000, 2)
        citations, invalid = ground_citations(text, hits)
        refused = reason is not None or is_refusal(text)
        yield {"event": "done", "refused": refused,
               "refusal_reason": reason or ("model_refused" if refused else None),
               "citations": [c.to_dict() for c in citations], "invalid_citations": invalid,
               "model": model, "usage": usage, "timings_ms": timings,
               "cost_usd": self._cost(model, usage) if model else None}


def from_env(index: Index) -> Assistant:
    """Assistant configured from environment variables (see config.py)."""
    from filing_assistant.config import get_settings

    s = get_settings()
    cfg = AssistantConfig(mode=s.retrieval_mode, embedder=s.embedder or None,
                          reranker=s.reranker, candidates=s.candidates, context=s.context_passages,
                          answer_mode=s.answer_mode, provider=s.llm_provider or None,
                          role=s.llm_role, use_tools=s.use_tools, route=s.route,
                          min_coverage=s.min_coverage, scope_guard=s.scope_guard,
                          mask_output_pii=s.mask_output_pii)
    if cfg.embedder and cfg.embedder not in index.dense:
        cfg.embedder = None
    if os.environ.get("FORCE_EXTRACTIVE") == "1":
        cfg.answer_mode = "extractive"
    return Assistant(index, cfg)

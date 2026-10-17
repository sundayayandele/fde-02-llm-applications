"""Filing assistant API: ask (JSON or streamed), search, filings, pages, ratio tool, UI.

Questions and answers are not logged; metrics carry counts, timings, tokens and cost only.
"""

from __future__ import annotations

import json
import time
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from prometheus_client import Counter, Histogram, make_asgi_app
from pydantic import BaseModel, Field

from filing_assistant import __version__
from filing_assistant.config import get_settings
from filing_assistant.tools import RatioError, compute_ratio, list_filings

settings = get_settings()
app = FastAPI(title="Filing assistant", version=__version__,
              description="Answers questions about company filings with page-level citations, "
                          "and says so when the filings do not contain the answer.")
app.mount("/metrics", make_asgi_app())
UI = Path(__file__).parent / "static" / "index.html"

REQUESTS = Counter("http_requests_total", "HTTP requests handled", ["method", "route", "status"])
LATENCY = Histogram("http_request_duration_seconds", "HTTP request duration", ["method", "route"])
QUESTIONS = Counter("questions_total", "Questions answered", ["mode", "outcome"])
ANSWER_SECONDS = Histogram("answer_seconds", "End-to-end answer time", ["mode"],
                           buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 30, 60))
TOKENS = Counter("llm_tokens_total", "LLM tokens used", ["kind"])
COST = Counter("llm_cost_usd_total", "Estimated LLM cost in USD (assumed prices)")
INVALID_CITATIONS = Counter("invalid_citations_total", "Citations pointing at no passage")


@lru_cache
def index():
    from filing_assistant.index import load
    root = Path(settings.index_dir)
    if not (root / "manifest.json").exists():
        return None
    return load(root)


@lru_cache
def assistant():
    from filing_assistant.pipeline import from_env
    idx = index()
    return from_env(idx) if idx is not None else None


def require_assistant():
    a = assistant()
    if a is None:
        raise HTTPException(status_code=503, detail="no index loaded; run `filing-assistant "
                            "ingest` or use an image with a baked index")
    return a


@app.middleware("http")
async def observe(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    # W3C trace context from an evaluation harness or gateway: echo the trace id so a run's
    # case can be matched to this request (v1.1; full OpenTelemetry instrumentation is later).
    traceparent = request.headers.get("traceparent", "")
    parts = traceparent.split("-")
    if len(parts) == 4 and len(parts[1]) == 32:
        response.headers["X-Trace-Id"] = parts[1]
    path = getattr(request.scope.get("route"), "path", "unmatched")
    REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    LATENCY.labels(request.method, path).observe(time.perf_counter() - started)
    return response


def _record(mode: str, refused: bool, seconds: float, usage: dict, cost: float | None,
            invalid: list[int]) -> None:
    QUESTIONS.labels(mode, "refused" if refused else "answered").inc()
    ANSWER_SECONDS.labels(mode).observe(seconds)
    TOKENS.labels("prompt").inc(usage.get("prompt_tokens", 0) or 0)
    TOKENS.labels("completion").inc(usage.get("completion_tokens", 0) or 0)
    if cost:
        COST.inc(cost)
    if invalid:
        INVALID_CITATIONS.inc(len(invalid))


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def ui() -> str:
    return UI.read_text(encoding="utf-8")


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict:
    """Ready when the process is up; reports whether an index is loaded and the answer mode."""
    idx = index()
    a = assistant()
    return {"status": "ready", "version": __version__, "environment": settings.environment,
            "index": idx is not None,
            "documents": len(idx.docs) if idx else 0,
            "chunks": len(idx.chunks) if idx else 0,
            "dense": sorted(idx.dense) if idx else [],
            "answer_mode": a.answer_mode() if a else None,
            "retrieval": a.config.mode if a else None}


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=settings.max_question_chars)
    docs: list[str] | None = Field(default=None, description="restrict to these filings")


@app.post("/api/v1/ask")
def ask(req: AskRequest) -> dict:
    a = require_assistant()
    t0 = time.perf_counter()
    answer = a.ask(req.question, docs=req.docs)
    _record(answer.mode, answer.refused, time.perf_counter() - t0, answer.usage,
            answer.cost_usd, answer.invalid_citations)
    return answer.to_dict()


@app.post("/api/v1/ask/stream")
def ask_stream(req: AskRequest) -> StreamingResponse:
    """Server-sent events: `hits`, then `token` events, then `done` with citations."""
    a = require_assistant()

    def events():
        t0 = time.perf_counter()
        mode = "extractive"
        try:
            for event in a.ask_stream(req.question, docs=req.docs):
                if event["event"] == "hits":
                    mode = event["mode"]
                if event["event"] == "done":
                    _record(mode, event["refused"], time.perf_counter() - t0, event["usage"],
                            event["cost_usd"], event["invalid_citations"])
                yield f"event: {event['event']}\ndata: {json.dumps(event, default=str)}\n\n"
        except Exception as e:  # noqa: BLE001 - report upstream failures to the client
            err = {"event": "error", "detail": type(e).__name__}
            yield f"event: error\ndata: {json.dumps(err)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=settings.max_question_chars)
    k: int = Field(default=5, ge=1, le=30)
    docs: list[str] | None = None


@app.post("/api/v1/search")
def search(req: SearchRequest) -> list[dict]:
    a = require_assistant()
    hits, _ = a.retrieve(req.query, req.docs)
    return [{"doc": h.chunk.doc, "page": h.chunk.page, "title": h.chunk.title,
             "kind": h.chunk.kind, "score": h.score, "rerank_score": h.rerank_score,
             "text": h.chunk.text} for h in hits[: req.k]]


@app.get("/api/v1/filings")
def filings(company: str | None = None, year: int | None = None,
            doc_type: str | None = Query(default=None, alias="type")) -> list[dict]:
    idx = index()
    if idx is None:
        return []
    return list_filings(idx.doc_info, idx.docs, company, year, doc_type)


@app.get("/api/v1/filings/{doc}/pages/{page}")
def page(doc: str, page: int) -> dict:
    idx = index()
    if idx is None or doc not in idx.docs:
        raise HTTPException(status_code=404, detail="unknown filing")
    text = idx.page_text(doc, page)
    if not text:
        raise HTTPException(status_code=404, detail="page not found or empty")
    return {"doc": doc, "page": page, "text": text}


@app.get("/api/v1/filings/{doc}/pdf", include_in_schema=False)
def pdf(doc: str) -> FileResponse:
    idx = index()
    if idx is None or doc not in idx.docs:
        raise HTTPException(status_code=404, detail="unknown filing")
    for folder in (Path(settings.data_dir) / "financebench" / "pdfs", Path(settings.data_dir)
                   / "demo", Path(settings.data_dir) / "pdfs", Path(settings.index_dir) / "pdfs"):
        path = folder / f"{doc}.pdf"
        if path.is_file():
            return FileResponse(path, media_type="application/pdf")
    raise HTTPException(status_code=404, detail="PDF not available on this server")


class RatioRequest(BaseModel):
    name: str
    values: dict[str, float]


@app.post("/api/v1/tools/ratio")
def ratio(req: RatioRequest) -> dict:
    try:
        return compute_ratio(req.name, req.values)
    except RatioError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None

"""Shared fixtures. INDEX_DIR points at an empty temp dir before the app is imported."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

_EMPTY = Path(tempfile.mkdtemp(prefix="fa-empty-"))
os.environ["INDEX_DIR"] = str(_EMPTY)
os.environ.pop("MISTRAL_API_KEY", None)

from filing_assistant.ingest import Chunk  # noqa: E402
from filing_assistant.retrieve import Hit  # noqa: E402


@pytest.fixture(scope="session")
def demo_dir(tmp_path_factory) -> Path:
    from filing_assistant.demo import write_demo_corpus
    folder = tmp_path_factory.mktemp("demo")
    write_demo_corpus(folder / "pdfs")
    return folder


@pytest.fixture(scope="session")
def demo_index(demo_dir):
    """Index of the demo corpus with LSA vectors (needs the ingestion exercises)."""
    from filing_assistant.demo import demo_doc_info
    from filing_assistant.index import build
    pdfs = sorted((demo_dir / "pdfs").glob("*.pdf"))
    return build(pdfs, demo_dir / "index", embedders=["lsa"],
                 doc_info=demo_doc_info(demo_dir / "pdfs"))


@pytest.fixture(scope="session")
def demo_questions(demo_dir):
    from filing_assistant.financebench import load_questions_file
    return load_questions_file(demo_dir / "pdfs" / "questions.json")


def make_hit(text: str, doc: str = "ACME_2023_10K", page: int = 1, kind: str = "text",
             title: str = "Section", score: float = 1.0) -> Hit:
    return Hit(0, Chunk(f"{doc}:{page}:0:x", doc, page, kind, title, text), score)


class FakeClient:
    """Stands in for LLMClient: scripted completions, streams and embeddings."""

    def __init__(self, replies=None, stream_parts=None):
        from filing_assistant.llm import Provider
        self.provider = Provider("fake", "http://fake", "FAKE_KEY", True,
                                 {"default": "fake-small", "strong": "fake-large",
                                  "embed": "fake-embed"},
                                 {"fake-small": {"input": 1.0, "output": 2.0},
                                  "fake-large": {"input": 1.0, "output": 2.0}})
        self.replies = list(replies or [])
        self.stream_parts = stream_parts or ["The answer ", "is 42 [1]."]
        self.calls: list[dict] = []

    def complete(self, messages, role="default", **params):
        self.calls.append({"messages": [dict(m) for m in messages], "params": params})
        reply = self.replies.pop(0) if self.replies else {"content": "ok [1]"}
        return {"content": reply.get("content"), "tool_calls": reply.get("tool_calls", []),
                "usage": reply.get("usage", {"prompt_tokens": 100, "completion_tokens": 10}),
                "model": self.provider.model_for(role)}

    def stream(self, messages, role="default", **params):
        self.calls.append({"messages": messages, "params": params, "stream": True})
        for part in self.stream_parts:
            yield {"delta": part}
        yield {"usage": {"prompt_tokens": 50, "completion_tokens": 5}}


def tool_call(name: str, arguments: dict, call_id: str = "call_1") -> dict:
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)}}

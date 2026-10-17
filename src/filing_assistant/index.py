"""The searchable index: chunks, BM25, and optional dense vectors, stored in one directory.

    <index_dir>/manifest.json    documents, pages, OCR pages, chunking parameters, build time
    <index_dir>/chunks.jsonl     one chunk per line (id, doc, page, kind, title, text)
    <index_dir>/lsa.joblib       offline dense embedder (TF-IDF + SVD), if built
    <index_dir>/dense-<name>.npy dense vectors per embedder (row i = chunk i)

BM25 is rebuilt from chunks.jsonl at load time (seconds), so no pickled index is shipped.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from filing_assistant import __version__
from filing_assistant.bm25 import BM25Index
from filing_assistant.ingest import Chunk, chunk_page, extract_pages
from filing_assistant.text import tokenize


@dataclass
class Index:
    root: Path
    chunks: list[Chunk]
    manifest: dict
    bm25: BM25Index
    dense: dict[str, np.ndarray] = field(default_factory=dict)
    _by_doc: dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def docs(self) -> list[str]:
        return sorted(self.manifest.get("documents", {}))

    @property
    def doc_info(self) -> dict[str, dict]:
        return {d: m.get("info", {}) for d, m in self.manifest.get("documents", {}).items()}

    def doc_mask(self, docs: list[str] | None) -> np.ndarray | None:
        if not docs:
            return None
        mask = np.zeros(len(self.chunks), dtype=bool)
        for doc in docs:
            if doc not in self._by_doc:
                self._by_doc[doc] = np.array([c.doc == doc for c in self.chunks])
            mask |= self._by_doc[doc]
        return mask

    def page_text(self, doc: str, page: int) -> str:
        parts = [c.text for c in self.chunks if c.doc == doc and c.page == page]
        return "\n\n".join(parts)


def build(pdf_paths: list[Path], root: Path, *, ocr: bool = True, max_words: int = 200,
          overlap: int = 40, embedders: list[str] | None = None,
          doc_info: dict[str, dict] | None = None, progress=None, guard: bool = True) -> Index:
    """Ingest PDFs, chunk them, write the index directory and fit/compute dense vectors.

    With `guard` (default), page text is cleaned before chunking (ADR-008): instruction-like
    sentences are quarantined and personal identifiers masked. What was removed or masked is
    recorded per document in the manifest, so a reviewer can see it."""
    from dataclasses import replace

    from filing_assistant.guardrails import mask_pii, quarantine

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    chunks: list[Chunk] = []
    documents: dict[str, dict] = {}
    for n, pdf in enumerate(sorted(pdf_paths), 1):
        pages = list(extract_pages(pdf, ocr=ocr))
        quarantined: list[dict] = []
        masked: dict[str, int] = {}
        pii_pages: list[int] = []
        if guard:
            cleaned = []
            for page in pages:
                text, removed = quarantine(page.text)
                text, kinds = mask_pii(text)
                quarantined += [{"page": page.page, "text": r[:500]} for r in removed]
                for kind in kinds:
                    masked[kind] = masked.get(kind, 0) + 1
                if kinds:
                    pii_pages.append(page.page)
                cleaned.append(replace(page, text=text))
            pages = cleaned
        doc_chunks = [c for p in pages for c in chunk_page(p, max_words, overlap)]
        chunks.extend(doc_chunks)
        documents[pdf.stem] = {"pages": len(pages), "chunks": len(doc_chunks),
                               "ocr_pages": [p.page for p in pages if p.ocr],
                               "empty_pages": [p.page for p in pages if not p.text.strip()],
                               "info": (doc_info or {}).get(pdf.stem, {}),
                               "guardrails": {"quarantined": quarantined,
                                              "pii_pages": pii_pages,
                                              "pii_pages_by_kind": masked}}
        if progress:
            progress(n, len(pdf_paths), pdf.stem)
    ingest_seconds = time.perf_counter() - t0
    with (root / "chunks.jsonl").open("w", encoding="utf-8") as handle:
        for c in chunks:
            handle.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
    manifest = {
        "package_version": __version__,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "chunking": {"max_words": max_words, "overlap": overlap, "ocr": ocr},
        "documents": documents,
        "totals": {"documents": len(documents), "pages": sum(d["pages"] for d in
                                                             documents.values()),
                   "chunks": len(chunks), "table_chunks": sum(c.kind == "table" for c in chunks),
                   "ocr_pages": sum(len(d["ocr_pages"]) for d in documents.values()),
                   "quarantined_sentences": sum(len(d["guardrails"]["quarantined"])
                                                for d in documents.values()),
                   "pii_masked_pages": sum(len(d["guardrails"]["pii_pages"])
                                           for d in documents.values())},
        "guarded": guard,
        "ingest_seconds": round(ingest_seconds, 1),
        "embedders": {},
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    index = load(root)
    for name in embedders or []:
        add_embeddings(index, name)
    return index


def add_embeddings(index: Index, name: str) -> None:
    """Compute and store dense vectors for every chunk with embedder `name`."""
    from filing_assistant.embed import get_embedder

    t0 = time.perf_counter()
    embedder = get_embedder(name, index.root, fit_texts=[c.for_index() for c in index.chunks])
    vectors, usage = embedder.embed_documents([c.for_index() for c in index.chunks])
    np.save(index.root / f"dense-{name}.npy", vectors.astype(np.float32))
    index.dense[name] = vectors.astype(np.float32)
    index.manifest["embedders"][name] = {"dim": int(vectors.shape[1]),
                                         "seconds": round(time.perf_counter() - t0, 1),
                                         "usage": usage, **embedder.describe()}
    (index.root / "manifest.json").write_text(json.dumps(index.manifest, indent=2))


def load(root: Path) -> Index:
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    chunks = []
    with (root / "chunks.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            chunks.append(Chunk(**json.loads(line)))
    bm25 = BM25Index([tokenize(c.for_index()) for c in chunks])
    dense = {p.stem.removeprefix("dense-"): np.load(p) for p in sorted(root.glob("dense-*.npy"))}
    return Index(root, chunks, manifest, bm25, dense)

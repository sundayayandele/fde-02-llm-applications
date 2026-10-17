"""Retrieval: BM25, dense, and hybrid (reciprocal rank fusion), optionally scoped to documents."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from filing_assistant.index import Index
from filing_assistant.ingest import Chunk
from filing_assistant.text import tokenize


@dataclass
class Hit:
    idx: int                  # position in index.chunks
    chunk: Chunk
    score: float              # fused (or single-retriever) score
    ranks: dict[str, int] = field(default_factory=dict)   # 1-based rank per retriever
    rerank_score: float | None = None

    @property
    def citation(self) -> str:
        return f"{self.chunk.doc} p.{self.chunk.page}"


def rrf_fuse(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """Reciprocal rank fusion: score(d) = Σ_r 1 / (k + rank_r(d)), rank starting at 1.

    `rankings` holds ranked lists of document ids (best first) from different retrievers.
    Return (id, score) pairs sorted by score descending, ties broken by smaller id.
    """
    # >>> SOLUTION: week-13 reciprocal rank fusion
    scores: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    # <<< SOLUTION


class Retriever:
    """mode: "bm25" | "dense" | "hybrid". `embedder` names the dense vectors to use."""

    def __init__(self, index: Index, *, mode: str = "hybrid", embedder: str | None = None,
                 candidates: int = 50, rewrite: bool = True) -> None:
        if mode not in {"bm25", "dense", "hybrid"}:
            raise ValueError("mode must be bm25, dense or hybrid")
        if mode != "bm25":
            if not index.dense:
                raise ValueError("this index has no dense vectors; build with --embed lsa|mistral"
                                 " or use mode=bm25")
            embedder = embedder or sorted(index.dense)[0]
            if embedder not in index.dense:
                raise ValueError(f"no '{embedder}' vectors in the index: {sorted(index.dense)}")
        self.index, self.mode, self.embedder_name = index, mode, embedder
        self.candidates = candidates
        self.rewrite = rewrite
        self._embedder = None

    def _embed_query(self, query: str) -> np.ndarray:
        if self._embedder is None:
            from filing_assistant.embed import get_embedder
            self._embedder = get_embedder(self.embedder_name, self.index.root)
        return self._embedder.embed_query(query)

    def _dense_rank(self, query: str, mask: np.ndarray | None, n: int) -> list[tuple[int, float]]:
        vectors = self.index.dense[self.embedder_name]
        sims = vectors @ self._embed_query(query)
        if mask is not None:
            sims = np.where(mask, sims, -np.inf)
        n = min(n, len(sims))
        idx = np.argpartition(-sims, n - 1)[:n]
        idx = idx[np.argsort(-sims[idx], kind="stable")]
        return [(int(i), float(sims[i])) for i in idx if np.isfinite(sims[i])]

    def search(self, query: str, k: int = 10, docs: list[str] | None = None) -> list[Hit]:
        if self.rewrite:
            from filing_assistant.query import rewrite
            query = rewrite(query)
        mask = self.index.doc_mask(docs)
        n = max(k, self.candidates)
        bm = self.index.bm25.top_k(tokenize(query), n, mask) if self.mode != "dense" else []
        dn = self._dense_rank(query, mask, n) if self.mode != "bm25" else []
        if self.mode == "bm25":
            fused, ranks = bm, {"bm25": bm}
        elif self.mode == "dense":
            fused, ranks = dn, {"dense": dn}
        else:
            fused = rrf_fuse([[i for i, _ in bm], [i for i, _ in dn]])
            ranks = {"bm25": bm, "dense": dn}
        rank_maps = {name: {i: r for r, (i, _) in enumerate(lst, 1)} for name, lst in ranks.items()}
        hits = []
        for i, score in fused[:k]:
            hits.append(Hit(i, self.index.chunks[i], float(score),
                            {name: m[i] for name, m in rank_maps.items() if i in m}))
        return hits

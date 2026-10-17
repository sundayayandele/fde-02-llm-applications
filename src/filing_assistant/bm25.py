"""BM25 (Okapi) written from scratch: inverted index, IDF, length-normalised term frequency.

    score(q, d) = Σ_t∈q  idf(t) · tf(t,d)·(k1+1) / (tf(t,d) + k1·(1 − b + b·|d|/avgdl))
    idf(t)      = ln( (N − df(t) + 0.5) / (df(t) + 0.5) + 1 )
"""

from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np


def bm25_idf(n_docs: int, df: int | np.ndarray) -> float | np.ndarray:
    """Inverse document frequency with BM25's smoothing (always positive):
    ln((N - df + 0.5) / (df + 0.5) + 1)."""
    # >>> SOLUTION: week-13 BM25 idf
    return np.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
    # <<< SOLUTION


def bm25_tf(tf: float | np.ndarray, doc_len: float | np.ndarray, avg_len: float,
            k1: float = 1.5, b: float = 0.75) -> float | np.ndarray:
    """Saturating, length-normalised term frequency:
    tf·(k1+1) / (tf + k1·(1 − b + b·doc_len/avg_len))."""
    # >>> SOLUTION: week-13 BM25 term frequency
    return tf * (k1 + 1) / (tf + k1 * (1 - b + b * doc_len / avg_len))
    # <<< SOLUTION


class BM25Index:
    """Inverted index over tokenised documents. Scores every document for a query at once."""

    def __init__(self, docs_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.n_docs = len(docs_tokens)
        self.doc_len = np.array([len(t) for t in docs_tokens], dtype=np.float32)
        self.avg_len = float(self.doc_len.mean()) if self.n_docs else 0.0
        postings: dict[str, tuple[list[int], list[int]]] = defaultdict(lambda: ([], []))
        for i, tokens in enumerate(docs_tokens):
            for term, tf in Counter(tokens).items():
                ids, tfs = postings[term]
                ids.append(i)
                tfs.append(tf)
        self.postings = {t: (np.array(ids, dtype=np.int32), np.array(tfs, dtype=np.float32))
                         for t, (ids, tfs) in postings.items()}

    def scores(self, query_tokens: list[str], mask: np.ndarray | None = None) -> np.ndarray:
        """BM25 score of every document (0 where no query term occurs). `mask` limits scoring
        to some documents (others get -inf)."""
        out = np.zeros(self.n_docs, dtype=np.float32)
        for term in set(query_tokens):
            if term not in self.postings:
                continue
            ids, tfs = self.postings[term]
            idf = bm25_idf(self.n_docs, len(ids))
            out[ids] += idf * bm25_tf(tfs, self.doc_len[ids], self.avg_len, self.k1, self.b)
        if mask is not None:
            out = np.where(mask, out, -np.inf)
        return out

    def top_k(self, query_tokens: list[str], k: int, mask: np.ndarray | None = None
              ) -> list[tuple[int, float]]:
        scores = self.scores(query_tokens, mask)
        if not len(scores):
            return []
        k = min(k, len(scores))
        idx = np.argpartition(-scores, k - 1)[:k]
        idx = idx[np.argsort(-scores[idx], kind="stable")]
        return [(int(i), float(scores[i])) for i in idx if scores[i] > 0]

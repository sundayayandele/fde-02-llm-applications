import math

import numpy as np
import pytest

from filing_assistant.bm25 import BM25Index, bm25_idf, bm25_tf
from filing_assistant.retrieve import Retriever, rrf_fuse

ex = pytest.mark.exercise


@ex
def test_idf_and_tf():
    assert bm25_idf(10, 1) == pytest.approx(math.log((10 - 1 + 0.5) / 1.5 + 1))
    assert bm25_idf(10, 10) > 0
    assert bm25_tf(1, 10, 10, k1=1.5, b=0.75) == pytest.approx(1.0)
    assert bm25_tf(3, 20, 10) < bm25_tf(3, 10, 10)          # longer docs score lower
    assert bm25_tf(100, 10, 10) < 1.5 + 1                     # saturates below k1 + 1
    assert np.allclose(bm25_tf(np.array([1.0, 2.0]), np.array([10.0, 10.0]), 10.0),
                       [1.0, bm25_tf(2, 10, 10)])


@ex
def test_bm25_ranks_and_masks():
    index = BM25Index([["capital", "expenditure", "cash"], ["revenue", "sales"],
                       ["capital", "capital", "lease"]])
    top = index.top_k(["capital", "expenditure"], 3)
    assert [i for i, _ in top] == [0, 2]
    masked = index.top_k(["capital"], 3, mask=np.array([False, True, True]))
    assert [i for i, _ in masked] == [2]
    assert index.top_k(["unknown"], 3) == []


@ex
def test_rrf_fuse():
    fused = rrf_fuse([[1, 2, 3], [3, 1]], k=60)
    assert [d for d, _ in fused] == [1, 3, 2]
    assert fused[0][1] == pytest.approx(1 / 61 + 1 / 62)
    assert rrf_fuse([[5], [4]]) == [(4, pytest.approx(1 / 61)), (5, pytest.approx(1 / 61))]
    assert rrf_fuse([]) == []


@ex
@pytest.mark.parametrize("mode", ["bm25", "dense", "hybrid"])
def test_retriever_modes_find_cash_flow_page(demo_index, mode):
    r = Retriever(demo_index, mode=mode, embedder="lsa")
    hits = r.search("Northwind capital expenditure FY2023", k=3)
    assert hits and hits[0].chunk.doc == "NORTHWIND_2023_10K"
    assert any(h.chunk.page == 5 for h in hits)
    assert all(h.citation.startswith("NORTHWIND") for h in hits)


@ex
def test_retriever_doc_scope_and_ranks(demo_index):
    r = Retriever(demo_index, mode="hybrid", embedder="lsa")
    hits = r.search("dividend per share", k=5, docs=["NORTHWIND_2023_EXHIBIT"])
    assert {h.chunk.doc for h in hits} == {"NORTHWIND_2023_EXHIBIT"}
    assert set(hits[0].ranks) <= {"bm25", "dense"}


@ex
def test_retriever_validates_mode(demo_index):
    with pytest.raises(ValueError):
        Retriever(demo_index, mode="magic")
    with pytest.raises(ValueError):
        Retriever(demo_index, mode="dense", embedder="mistral")

# Week 13: Retrieval: BM25, dense and hybrid

**Goal:** build keyword search from first principles, combine it with dense vectors, and measure what each improvement buys.

## Brief

The model can only cite what retrieval finds. Your job this week is to get the right page into the top five as often as possible, and to prove it with numbers.

## Concepts

Inverted indexes; TF-IDF and BM25 (k1, b, saturation, length normalisation); dense embeddings (LSA offline, `mistral-embed`); cosine similarity; reciprocal rank fusion; query rewriting; metadata routing; recall@k and MRR.

## Steps

1. Implement `bm25_idf` and `bm25_tf` in `bm25.py` from the formulas in the module docstring.
2. Implement `rrf_fuse(rankings, k)` in `retrieve.py`.
3. `pytest tests/test_bm25_retrieve.py -m exercise`.
4. `filing-assistant eval-retrieval` (FinanceBench index from week 12). Fill this table from the output (scope `doc`, recall@5): BM25 raw → + rewrite → + lexical rerank → hybrid.
5. Read `query.py` (glossary) and `router.py` (company and year). Compare the `routed` and `corpus` scopes. Why does routing matter so much on a multi-company corpus?
6. With a key (optional): `make embed-mistral` and re-run with `--only hybrid dense`. Does `mistral-embed` beat LSA?

## Check

```bash
pytest tests/test_bm25_retrieve.py -m exercise && filing-assistant eval-retrieval --only bm25
```

## Evidence

Your ablation table (four rows, recall@5 and MRR) and two misses from the report with a sentence each on why they failed.

## Stretch

Add five glossary entries from misses on the **dev** half only (`--split dev`), then check the **test** half. Did recall move? This is the honest way to tune.

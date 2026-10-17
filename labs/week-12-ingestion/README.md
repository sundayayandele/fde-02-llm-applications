# Week 12: Ingestion: PDFs, OCR and tables

**Goal:** turn real filings, including scanned pages and financial statements, into chunks that keep their meaning and their page numbers.

## Brief

Analysts care most about the statements: cash flows, balance sheets, income statements. A chunker that cuts a statement in half, or loses which year a column is, will give wrong answers however good the model is.

## Concepts

PDF text layers vs scanned images; OCR (Tesseract); reading order; tables as Markdown; chunk size and overlap; contextual chunk headers; provenance (document and page on every chunk).

## Steps

1. `make ingest-demo`, then open `index/chunks.jsonl`. Find the Northwind cash flow table and the OCR'd exhibit (`meta.ocr`).
2. Implement `table_to_markdown(rows)` in `ingest.py`: header row, separator, body; pad short rows; replace `|` inside cells.
3. Implement `chunk_text(text, max_words, overlap)`: sliding windows that share `overlap` words, with no window that adds nothing new.
4. `pytest tests/test_ingest.py -m exercise`.
5. `make download` (about 160 MB), then `make ingest` (about 6 minutes). Read `index/manifest.json`: how many pages needed OCR? How many chunks are tables?
6. Look at 3M's FY2018 cash flow statement (page 60) in `chunks.jsonl`. Is "Purchases of property, plant and equipment" in the same chunk as the year header?

## Check

```bash
pytest tests/test_ingest.py -m exercise && make ingest-demo
```

## Evidence

The manifest totals, one table chunk you are proud of, and one you are not (and why).

## Stretch

Measure retrieval recall with `--max-words 120` and `--max-words 320` (re-ingest each time, then `filing-assistant eval-retrieval --only bm25`). Which size wins, and why might tables and prose want different sizes?

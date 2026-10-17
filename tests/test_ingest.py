import shutil

import pytest

from filing_assistant.ingest import (
    Page,
    blocks,
    chunk_page,
    chunk_text,
    extract_pages,
    is_numeric_row,
    page_title,
    split_row,
    table_to_markdown,
)

ex = pytest.mark.exercise


def test_numeric_rows():
    assert is_numeric_row("Net income $ 5,363 $ 4,869 $ 5,058")
    assert is_numeric_row("Gain on sale (545) (586) (111)")
    assert not is_numeric_row("Cash Flows from Operating Activities")
    assert not is_numeric_row("")
    assert split_row("Net income $ 5,363 $ 4,869") == ["Net income", "$5,363", "$4,869"]
    assert split_row("Other — net 120 — 76") == ["Other — net", "120", "—", "76"]


@ex
def test_table_to_markdown():
    md = table_to_markdown([["(Millions)", "2023", "2022"], ["Net sales", "5,400"],
                            ["A|B", " 1 ", "2"]])
    assert md.splitlines() == ["| (Millions) | 2023 | 2022 |", "| --- | --- | --- |",
                               "| Net sales | 5,400 |  |", "| A/B | 1 | 2 |"]
    assert table_to_markdown([]) == ""


@ex
def test_chunk_text_windows():
    words = " ".join(str(i) for i in range(10))
    assert chunk_text(words, max_words=4, overlap=1) == ["0 1 2 3", "3 4 5 6", "6 7 8 9"]
    assert chunk_text("  a   b ", max_words=4, overlap=1) == ["a b"]
    assert chunk_text("", 4, 1) == []
    assert chunk_text(" ".join("x" * 1 for _ in range(5)), 5, 2) == ["x x x x x"]


def test_chunk_text_rejects_bad_overlap():
    with pytest.raises(ValueError):
        chunk_text("a b", max_words=2, overlap=2)


@ex
def test_blocks_keep_statement_tables_whole():
    text = "\n".join([
        "Consolidated Statements of Cash Flows", "(Millions) 2023 2022 2021",
        "Net income $ 585 $ 475 $ 403", "Adjustments to reconcile net income",
        "Depreciation 210 195 180", "Purchases of property and equipment (285) (240) (210)",
        "Narrative text follows here."])
    out = blocks(text)
    assert [k for k, _ in out] == ["text", "table", "text"]
    table = out[1][1]
    assert table.startswith("| (Millions) | 2023 | 2022 | 2021 |")
    assert "| Adjustments to reconcile net income |" in table


def test_page_title_prefers_statement_names():
    assert page_title("Table of Contents\nACME Inc.\nConsolidated Balance Sheets\n1 2 3") == \
        "Consolidated Balance Sheets"
    assert page_title("Item 1. Business\nWe sell things.") == "Item 1. Business"
    assert page_title("") == ""


@ex
def test_chunk_page_headers_and_kinds():
    page = Page("ACME_2023_10K", 5, "Consolidated Statements of Income\n(Millions) 2023 2022\n"
                "Net sales 10 9\nCost of sales 6 5\nNet income 2 1\n" + "word " * 450)
    chunks = chunk_page(page, max_words=200, overlap=40)
    tables = [c for c in chunks if c.kind == "table"]
    assert len(tables) == 1 and tables[0].text.startswith("| (Millions) | 2023 | 2022 |")
    assert tables[0].header == "[ACME_2023_10K p.5] Consolidated Statements of Income"
    assert all(c.title == "Consolidated Statements of Income" for c in chunks)
    assert sum(c.kind == "text" for c in chunks) >= 3
    assert len({c.id for c in chunks}) == len(chunks)


def test_extract_pages_text_layer(demo_dir):
    pages = list(extract_pages(demo_dir / "pdfs" / "NORTHWIND_2023_10K.pdf", ocr=False))
    assert [p.page for p in pages] == [1, 2, 3, 4, 5]
    assert "Purchases of property and equipment (285)" in pages[4].text
    assert not any(p.ocr for p in pages)


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_extract_pages_ocr_for_scanned_page(demo_dir):
    [page] = list(extract_pages(demo_dir / "pdfs" / "NORTHWIND_2023_EXHIBIT.pdf"))
    assert page.ocr and "0.55" in page.text
    [no_ocr] = list(extract_pages(demo_dir / "pdfs" / "NORTHWIND_2023_EXHIBIT.pdf", ocr=False))
    assert no_ocr.text.strip() == "" and not no_ocr.ocr

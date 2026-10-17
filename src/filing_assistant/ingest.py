"""PDF ingestion: pages → text and table blocks → chunks with page-level provenance.

- Text comes from PDFium (fast, keeps table rows on one line).
- Pages without a text layer are OCR'd with Tesseract (scanned filings, image-only exhibits).
- Financial tables are kept whole: runs of lines that end in numbers become one "table" block,
  rendered as Markdown when the columns line up, so a chunk never splits a statement in half.
- Every chunk carries a contextual header (document, page, section title), which helps both
  retrieval and the model's citations.

Page numbers are 1-based everywhere in this package (FinanceBench's evidence pages are 0-based
and are converted when loaded).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

_NUM = r"\(?-?\$?\s?\d[\d,]*(?:\.\d+)?%?\)?"
_SPACE = re.compile(r"[ \t]+")


@dataclass
class Page:
    doc: str
    page: int                 # 1-based
    text: str
    ocr: bool = False


@dataclass
class Chunk:
    id: str
    doc: str
    page: int                 # 1-based
    kind: str                 # "text" | "table"
    title: str
    text: str                 # body without header
    meta: dict = field(default_factory=dict)

    @property
    def header(self) -> str:
        return f"[{self.doc} p.{self.page}] {self.title}".strip()

    def for_index(self) -> str:
        """Text used for retrieval: contextual header + body."""
        return f"{self.header}\n{self.text}"

    def to_dict(self) -> dict:
        return asdict(self)


# ---- page extraction ------------------------------------------------------------------

def extract_pages(pdf_path: Path, *, ocr: bool = True, min_chars: int = 40,
                  ocr_dpi: int = 200) -> Iterator[Page]:
    """Yield one Page per PDF page. Pages with fewer than `min_chars` characters of text are
    OCR'd when `ocr` is true (needs the `tesseract` binary)."""
    import pypdfium2 as pdfium

    doc_name = Path(pdf_path).stem
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            text = page.get_textpage().get_text_range().replace("\r", "")
            used_ocr = False
            if ocr and len(text.strip()) < min_chars:
                ocr_text = ocr_page(page, dpi=ocr_dpi)
                if len(ocr_text.strip()) > len(text.strip()):
                    text, used_ocr = ocr_text, True
            yield Page(doc_name, i + 1, text, used_ocr)
    finally:
        pdf.close()


def ocr_page(page, dpi: int = 200) -> str:
    """Render one PDFium page and run Tesseract on it. Returns '' if Tesseract is missing."""
    try:
        import pytesseract
    except ImportError:  # pragma: no cover - optional dependency
        return ""
    image = page.render(scale=dpi / 72).to_pil()
    try:
        return pytesseract.image_to_string(image, config="--psm 6")
    except pytesseract.TesseractNotFoundError:  # pragma: no cover - binary missing
        return ""


# ---- blocks and tables ----------------------------------------------------------------

def is_numeric_row(line: str) -> bool:
    """A line that ends with at least one number-like value (a table row)."""
    line = line.strip()
    if not line or len(line) > 400:
        return False
    tokens = line.split()
    trailing = 0
    for tok in reversed(tokens):
        if re.fullmatch(rf"{_NUM}|\$|—|-|–", tok):
            trailing += 1
        else:
            break
    return trailing >= 1 and any(ch.isdigit() for ch in line)


def split_row(line: str) -> list[str]:
    """Split a table row into label + value cells ("Net income $ 5,363 $ 4,869" →
    ["Net income", "$5,363", "$4,869"])."""
    tokens = line.strip().split()
    values: list[str] = []
    while tokens and re.fullmatch(rf"{_NUM}|\$|—|-|–", tokens[-1]):
        tok = tokens.pop()
        if tok == "$" and values:
            values[0] = "$" + values[0]
        elif tok != "$":
            values.insert(0, tok)
    return [" ".join(tokens)] + values


def table_to_markdown(rows: list[list[str]]) -> str:
    """Render rows as a Markdown table. The first row is the header.

    - Pad short rows with empty cells so every row has as many cells as the longest row.
    - Strip whitespace in cells and replace '|' inside a cell with '/'.
    - Emit: header row, a separator row of '---' cells, then the body rows, each line as
      "| a | b |". Return '' for no rows.
    """
    # >>> SOLUTION: week-12 table to Markdown
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    clean = [[(c or "").strip().replace("|", "/") for c in r] + [""] * (width - len(r))
             for r in rows]
    lines = ["| " + " | ".join(clean[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in clean[1:]]
    return "\n".join(lines)
    # <<< SOLUTION


def blocks(text: str, min_table_rows: int = 3, max_gap: int = 2) -> list[tuple[str, str]]:
    """Split page text into ("text", ...) and ("table", ...) blocks.

    A table is a run of at least `min_table_rows` numeric rows. Up to `max_gap` short
    non-numeric lines inside a run (sub-headings such as "Cash Flows from Investing
    Activities") stay in the table as label rows. The line just before the run is kept as
    the table's column header when it mentions years or units ("(Millions)").
    """
    lines = [_SPACE.sub(" ", ln).strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    numeric = [is_numeric_row(ln) for ln in lines]
    out: list[tuple[str, str]] = []
    buf: list[str] = []
    i = 0
    while i < len(lines):
        if not numeric[i]:
            buf.append(lines[i])
            i += 1
            continue
        end, j = i, i
        while j < len(lines):
            if numeric[j]:
                end = j
                j += 1
                continue
            gap = j
            while gap < len(lines) and not numeric[gap] and gap - j < max_gap \
                    and len(lines[gap]) <= 120:
                gap += 1
            if gap < len(lines) and numeric[gap] and gap - j <= max_gap:
                j = gap
                continue
            break
        run = lines[i:end + 1]
        if sum(numeric[i:end + 1]) < min_table_rows:
            buf.extend(run)
            i = end + 1
            continue
        header = None
        if buf and re.search(r"\b(19|20)\d{2}\b|millions|thousands|years ended", buf[-1], re.I):
            header = buf.pop()
        if buf:
            out.append(("text", "\n".join(buf)))
            buf = []
        rows = ([split_row(header)] if header else []) + \
            [split_row(r) if is_numeric_row(r) else [r] for r in run]
        out.append(("table", table_to_markdown(rows)))
        i = end + 1
    if buf:
        out.append(("text", "\n".join(buf)))
    return out


_TITLE_HINT = re.compile(r"consolidated|statements? of|balance sheets?|^note \d|^item \d|"
                         r"management.s discussion|results of operations|segment|"
                         r"cash flows|income|revenue", re.I)


def page_title(text: str, max_len: int = 120) -> str:
    """A short section title for the page: the first heading-like line among the first
    eight meaningful lines (statement names, "Note 5", "Item 7"), else the first line."""
    candidates = []
    for line in text.split("\n"):
        line = _SPACE.sub(" ", line).strip()
        if not line or line.lower().startswith("table of contents") or line.isdigit():
            continue
        if len(line) >= 4 and not is_numeric_row(line):
            candidates.append(line)
        if len(candidates) == 8:
            break
    for line in candidates:
        if _TITLE_HINT.search(line) and len(line) <= max_len:
            return line
    return candidates[0][:max_len] if candidates else ""


# ---- chunking -------------------------------------------------------------------------

def chunk_text(text: str, max_words: int = 200, overlap: int = 40) -> list[str]:
    """Split text into windows of at most `max_words` words; consecutive windows share
    `overlap` words. Whitespace is normalised to single spaces. Empty text gives [].

    Example: 10 words, max_words=4, overlap=1 → words[0:4], words[3:7], words[6:10].
    The last window may be shorter; never emit a window that adds no new words.
    """
    if overlap >= max_words:
        raise ValueError("overlap must be smaller than max_words")
    # >>> SOLUTION: week-12 sliding-window chunking
    words = text.split()
    if not words:
        return []
    step = max_words - overlap
    out = []
    for start in range(0, len(words), step):
        out.append(" ".join(words[start:start + max_words]))
        if start + max_words >= len(words):
            break
    return out
    # <<< SOLUTION


def chunk_page(page: Page, max_words: int = 200, overlap: int = 40,
               max_table_words: int = 600) -> list[Chunk]:
    """Chunks for one page: tables kept whole (split by rows only when very large), text
    split with overlap. Each chunk gets the page title as its section title."""
    title = page_title(page.text)
    chunks: list[Chunk] = []

    def add(kind: str, body: str) -> None:
        digest = hashlib.sha1(f"{page.doc}|{page.page}|{len(chunks)}|{body}".encode(),
                              usedforsecurity=False).hexdigest()[:10]
        chunks.append(Chunk(f"{page.doc}:{page.page}:{len(chunks)}:{digest}", page.doc,
                            page.page, kind, title, body, {"ocr": page.ocr}))

    text_parts: list[str] = []
    for kind, body in blocks(page.text):
        if kind == "table":
            if text_parts:
                for window in chunk_text(" ".join(text_parts), max_words, overlap):
                    add("text", window)
                text_parts = []
            rows = body.split("\n")
            if len(body.split()) <= max_table_words or len(rows) <= 4:
                add("table", body)
            else:
                head, rest = rows[:2], rows[2:]
                size = max(4, len(rest) * max_table_words // max(1, len(body.split())))
                for s in range(0, len(rest), size):
                    add("table", "\n".join(head + rest[s:s + size]))
        else:
            text_parts.append(body)
    if text_parts:
        for window in chunk_text(" ".join(text_parts), max_words, overlap):
            add("text", window)
    return chunks

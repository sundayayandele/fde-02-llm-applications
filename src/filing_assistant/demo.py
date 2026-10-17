"""A small, fictional demo corpus: offline, licence-free, used by tests, `make e2e`, labs and
offline image builds.

"Northwind Retail Inc." does not exist. Its two filings are generated as real PDFs: a
text-layer 10-K (statements as tables, MD&A prose) and a scanned exhibit (an image-only page,
so ingestion has to OCR it).
"""

from __future__ import annotations

import json
from pathlib import Path

PAGES_10K: list[list[str]] = [
    ["UNITED STATES SECURITIES AND EXCHANGE COMMISSION", "FORM 10-K",
     "Northwind Retail Inc.", "Fiscal year ended December 31, 2023",
     "This document is fictional and exists for software testing only."],
    ["Item 7. Management's Discussion and Analysis",
     "Net sales increased 8.0 percent to $5,400 million in fiscal 2023, driven by",
     "higher store traffic and growth in online orders. Gross margin improved to 40.0",
     "percent from 38.0 percent as freight costs eased. Operating income rose to",
     "$810 million. We opened 25 new stores and closed 4, ending the year with 412 stores.",
     "Management expects capital expenditures of about $300 million in fiscal 2024."],
    ["Consolidated Statements of Income", "(Millions) 2023 2022 2021",
     "Net sales $ 5,400 $ 5,000 $ 4,600", "Cost of sales 3,240 3,100 2,900",
     "Gross profit 2,160 1,900 1,700", "Selling, general and administrative 1,350 1,230 1,120",
     "Operating income 810 670 580", "Interest expense 40 45 50",
     "Income before income taxes 770 625 530", "Provision for income taxes 185 150 127",
     "Net income $ 585 $ 475 $ 403"],
    ["Consolidated Balance Sheets", "(Millions) 2023 2022",
     "Cash and cash equivalents $ 620 $ 480", "Inventories 1,150 1,090",
     "Total current assets 2,300 2,050", "Property and equipment, net 1,900 1,780",
     "Total assets 4,600 4,250", "Total current liabilities 1,400 1,310",
     "Long-term debt 900 1,000", "Total shareholders' equity 1,950 1,700"],
    ["Consolidated Statements of Cash Flows", "(Millions) 2023 2022 2021",
     "Net income $ 585 $ 475 $ 403", "Depreciation and amortization 210 195 180",
     "Net cash provided by operating activities 905 760 690",
     "Purchases of property and equipment (285) (240) (210)",
     "Net cash used in investing activities (290) (250) (215)",
     "Dividends paid (215) (190) (170)",
     "Net cash used in financing activities (475) (420) (380)"],
]

EXHIBIT_LINES = ["Exhibit 99.1 - Board resolution", "Northwind Retail Inc.",
                 "Quarterly dividend declared per share: $0.55",
                 "Payable on March 15, 2024 to holders of record on March 1, 2024."]

QUESTIONS = [
    {"id": "demo-1", "doc": "NORTHWIND_2023_10K", "evidence_pages": [5],
     "question": "What was Northwind's FY2023 capital expenditure in USD millions?",
     "answer": "$285 million"},
    {"id": "demo-2", "doc": "NORTHWIND_2023_10K", "evidence_pages": [3],
     "question": "What was Northwind's net income in FY2022?", "answer": "$475 million"},
    {"id": "demo-3", "doc": "NORTHWIND_2023_10K", "evidence_pages": [4],
     "question": "What were Northwind's total current assets at the end of FY2023?",
     "answer": "$2,300 million"},
    {"id": "demo-4", "doc": "NORTHWIND_2023_EXHIBIT", "evidence_pages": [1],
     "question": "What quarterly dividend per share did Northwind declare?",
     "answer": "$0.55"},
]


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_text_pdf(path: Path, pages: list[list[str]]) -> Path:
    """Write a minimal, valid PDF with one Helvetica text line per list item."""
    objects: list[bytes] = []
    page_ids = [3 + 2 * i for i in range(len(pages))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    font_id = 3 + 2 * len(pages)
    for i, lines in enumerate(pages):
        stream = ["BT /F1 11 Tf 14 TL 60 740 Td"]
        stream += [f"({_escape(line)}) '" for line in lines]
        stream.append("ET")
        content = "\n".join(stream).encode("latin-1")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                       f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                       f"/Contents {page_ids[i] + 1} 0 R >>".encode())
        objects.append(f"<< /Length {len(content)} >>\nstream\n".encode() + content
                       + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
            .encode())
    Path(path).write_bytes(bytes(out))
    return Path(path)


def write_scanned_pdf(path: Path, lines: list[str]) -> Path:
    """An image-only PDF page (no text layer), like a scanned exhibit."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1700, 2200), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.load_default(size=48)
    except TypeError:  # pragma: no cover - Pillow < 10.1
        font = ImageFont.load_default()
    y = 200
    for line in lines:
        draw.text((150, y), line, fill="black", font=font)
        y += 90
    image.save(path, "PDF", resolution=200.0)
    return Path(path)


def write_demo_corpus(folder: Path) -> list[Path]:
    """Create the demo PDFs, document metadata and questions in `folder`."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    pdfs = [write_text_pdf(folder / "NORTHWIND_2023_10K.pdf", PAGES_10K),
            write_scanned_pdf(folder / "NORTHWIND_2023_EXHIBIT.pdf", EXHIBIT_LINES)]
    info = {"NORTHWIND_2023_10K": {"company": "Northwind Retail", "doc_type": "10k",
                                   "doc_period": 2023, "gics_sector": "Consumer Discretionary"},
            "NORTHWIND_2023_EXHIBIT": {"company": "Northwind Retail", "doc_type": "8k",
                                       "doc_period": 2023,
                                       "gics_sector": "Consumer Discretionary"}}
    (folder / "doc_info.json").write_text(json.dumps(info, indent=2))
    (folder / "questions.json").write_text(json.dumps(QUESTIONS, indent=2))
    return pdfs


def demo_doc_info(folder: Path) -> dict[str, dict]:
    path = Path(folder) / "doc_info.json"
    return json.loads(path.read_text()) if path.exists() else {}

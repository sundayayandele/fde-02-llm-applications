"""FinanceBench (open-source sample): 150 questions over 84 public company filings.

Source: https://github.com/patronus-ai/financebench, pinned to a commit. The question file and
the PDFs are downloaded at run time and checked; nothing is committed. Evidence page numbers in
the source are 0-based; here they are converted to the package's 1-based pages.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import httpx

COMMIT = "cc39aeb4afdf33909ee1412188bf89035950c2eb"
BASE = f"https://raw.githubusercontent.com/patronus-ai/financebench/{COMMIT}"
QUESTIONS = "financebench_open_source.jsonl"
DOC_INFO = "financebench_document_information.jsonl"
SHA256 = {
    QUESTIONS: "a5a2aa673e573e55675fc3c0f9aa38c1cf59d2abc91edb077534f71f10a71877",
    DOC_INFO: "1c69127783879de8cdadb159d2181f39bc3123b8e0ebf74031c3969d69189575",
}


@dataclass
class Question:
    id: str
    company: str
    doc: str
    question: str
    answer: str
    type: str                       # metrics-generated | domain-relevant | novel-generated
    reasoning: str | None
    evidence_pages: list[int] = field(default_factory=list)   # 1-based
    justification: str = ""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(data_dir: Path, *, docs: list[str] | None = None,
             client: httpx.Client | None = None) -> Path:
    """Download question and document files, then the PDFs (all question docs, or `docs`)."""
    root = Path(data_dir) / "financebench"
    (root / "pdfs").mkdir(parents=True, exist_ok=True)
    http = client or httpx.Client(timeout=120, follow_redirects=True)
    try:
        for name, expected in SHA256.items():
            path = root / name
            if not path.exists() or _sha256(path.read_bytes()) != expected:
                response = http.get(f"{BASE}/data/{name}")
                response.raise_for_status()
                if _sha256(response.content) != expected:
                    raise ValueError(f"{name}: checksum does not match the pinned file")
                path.write_bytes(response.content)
        wanted = docs if docs is not None else sorted({q.doc for q in load_questions(data_dir)})
        for doc in wanted:
            pdf = root / "pdfs" / f"{doc}.pdf"
            if pdf.exists() and pdf.stat().st_size > 0:
                continue
            response = http.get(f"{BASE}/pdfs/{doc}.pdf")
            response.raise_for_status()
            if not response.content.startswith(b"%PDF"):
                raise ValueError(f"{doc}: download is not a PDF")
            pdf.write_bytes(response.content)
    finally:
        if client is None:
            http.close()
    return root


def load_questions(data_dir: Path) -> list[Question]:
    path = Path(data_dir) / "financebench" / QUESTIONS
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        pages = sorted({int(e["evidence_page_num"]) + 1 for e in row.get("evidence", [])
                        if e.get("evidence_page_num") is not None})
        out.append(Question(row["financebench_id"], row["company"], row["doc_name"],
                            row["question"], str(row["answer"]), row["question_type"],
                            row.get("question_reasoning"), pages,
                            row.get("justification") or ""))
    return out


def split_of(question_id: str) -> str:
    """Deterministic half split: "dev" for tuning thresholds, "test" for reporting."""
    digest = hashlib.sha1(question_id.encode(), usedforsecurity=False).hexdigest()
    return "dev" if int(digest, 16) % 2 == 0 else "test"


def load_doc_info(data_dir: Path) -> dict[str, dict]:
    """doc_name → {company, gics_sector, doc_type, doc_period, doc_link}."""
    path = Path(data_dir) / "financebench" / DOC_INFO
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return {r["doc_name"]: r for r in rows}


def load_questions_file(path: Path) -> list[Question]:
    """Questions from a JSON list (the demo corpus format): id, doc, question, answer,
    evidence_pages (1-based), optional type and company."""
    import json as _json
    rows = _json.loads(Path(path).read_text(encoding="utf-8"))
    return [Question(r["id"], r.get("company", r["doc"].split("_")[0]), r["doc"], r["question"],
                     str(r["answer"]), r.get("type", "metrics-generated"), None,
                     list(r.get("evidence_pages", []))) for r in rows]

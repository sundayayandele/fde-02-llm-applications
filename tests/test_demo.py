from filing_assistant.demo import QUESTIONS, write_text_pdf


def test_text_pdf_is_valid(tmp_path):
    import pypdfium2 as pdfium
    path = write_text_pdf(tmp_path / "x.pdf", [["Hello (world)"], ["Second page"]])
    pdf = pdfium.PdfDocument(str(path))
    assert len(pdf) == 2
    assert "Hello (world)" in pdf[0].get_textpage().get_text_range()
    pdf.close()
    assert all(q["evidence_pages"] for q in QUESTIONS)

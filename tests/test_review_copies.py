"""Review copies must contain only reconstructed redacted text, not source bytes."""
import zipfile

import pytest

from cadence_pii.models import Block, Document, FileResult, Finding, Status
from cadence_pii.redact import redact
from cadence_pii.review_copies import export_review_copy


@pytest.mark.parametrize("ext", ["pdf", "docx", "pptx"])
def test_review_copy_same_extension_contains_placeholder_not_raw(tmp_path, ext):
    original = "Contact Mira Vale at mira@example.com for review."
    doc = Document(filename=f"sample.{ext}", filetype=ext,
                   blocks=[Block(1, "page 1 / paragraph", "paragraph", original, "native", 1)])
    doc.assemble()
    start = doc.text.index("mira@example.com")
    finding = Finding("EMAIL", start, start + len("mira@example.com"), "mira@example.com",
                      0.99, "regex", "email", block_id=1, locator="page 1 / paragraph")
    cleaned, _ = redact(doc.text, [finding])
    result = FileResult(filename=doc.filename, filetype=ext, status=Status.REVIEW_REQUIRED,
                        document=doc, findings=[finding], redacted_text=cleaned)
    output = export_review_copy(result, tmp_path)
    assert output.suffix == f".{ext}"
    if ext == "pdf":
        import pymupdf
        with pymupdf.open(output) as pdf:
            rendered = "\n".join(page.get_text() for page in pdf)
    elif ext == "docx":
        from docx import Document as WordDocument
        rendered = "\n".join(p.text for p in WordDocument(output).paragraphs)
    else:
        from pptx import Presentation
        rendered = "\n".join(shape.text for slide in Presentation(output).slides
                             for shape in slide.shapes if shape.has_text_frame)
    assert "[EMAIL_1]" in rendered
    assert "mira@example.com" not in rendered
    assert "REVIEW COPY" in rendered
    if ext in ("docx", "pptx"):
        with zipfile.ZipFile(output) as archive:
            assert b"mira@example.com" not in b"".join(archive.read(n) for n in archive.namelist())


def test_review_copy_refuses_unmatched_final_text(tmp_path):
    doc = Document(filename="sample.pdf", filetype="pdf",
                   blocks=[Block(1, "page 1", "paragraph", "raw@example.com", "native", 1)])
    doc.assemble()
    result = FileResult(filename=doc.filename, status=Status.CLEARED, document=doc,
                        redacted_text="[EMAIL_1]")
    with pytest.raises(ValueError, match="does not match"):
        export_review_copy(result, tmp_path)
    assert list(tmp_path.iterdir()) == []

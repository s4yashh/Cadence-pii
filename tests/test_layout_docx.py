"""Word visual draft preserves its document structure while masking editable text."""
import hashlib

from cadence_pii.extract.native_ext import extract_native
from cadence_pii.layout_docx import redact_original_docx
from cadence_pii.models import FileResult, Finding, Status


def test_layout_docx_preserves_tables_and_replaces_merged_name_finding(tmp_path):
    from docx import Document

    source = tmp_path / "sample.docx"
    original = Document()
    original.add_heading("Contacts", 1)
    original.add_paragraph("Email mira@example.com")
    table = original.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Names"
    table.cell(0, 1).text = "Role"
    table.cell(1, 0).text = "Mira Vale\nRowan Stone"
    table.cell(1, 1).text = "Reviewers"
    original.save(source)

    doc = extract_native(source, ocr=False)
    position = doc.text.index("Mira Vale")
    merged = Finding("PERSON", position, position + len("Mira Vale Rowan Stone"),
                     "Mira Vale Rowan Stone", .9, "test", "test")
    result = FileResult(filename=source.name, status=Status.REVIEW_REQUIRED,
                        document=doc, findings=[merged],
                        sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    target = tmp_path / "sample.editable_text_redacted.review.docx"
    stats = redact_original_docx(source, result, target)

    before, after = Document(source), Document(target)
    assert len(before.paragraphs) == len(after.paragraphs)
    assert len(before.tables) == len(after.tables) == 1
    assert [(len(t.rows), len(t.columns)) for t in before.tables] == [
        (len(t.rows), len(t.columns)) for t in after.tables]
    text = "\n".join(p.text for p in after.paragraphs) + after.tables[0].cell(1, 0).text
    assert "mira@example.com" not in text
    assert "Mira Vale" not in text and "Rowan Stone" not in text
    assert "[EMAIL_" in text and "[PERSON_" in text
    assert stats["editable_replacements"] >= 3

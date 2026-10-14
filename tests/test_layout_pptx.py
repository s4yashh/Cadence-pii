"""The original-layout PPTX changes editable PII text without moving shapes."""
import hashlib

from cadence_pii.extract.native_ext import extract_native
from cadence_pii.layout_pptx import redact_original_pptx
from cadence_pii.models import FileResult, Finding, Status
from cadence_pii.redact import redact


def test_layout_pptx_preserves_shapes_and_masks_table_and_split_run(tmp_path):
    from pptx import Presentation
    from pptx.util import Inches

    source = tmp_path / "sample.pptx"
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(1))
    para = box.text_frame.paragraphs[0]
    para.add_run().text = "Contact mira@"
    para.add_run().text = "example.com today"
    table = slide.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(7), Inches(2)).table
    table.cell(0, 0).text = "Name"
    table.cell(0, 1).text = "Role"
    table.cell(1, 0).text = "Mira Vale"
    table.cell(1, 1).text = "Reviewer"
    prs.save(source)

    doc = extract_native(source, ocr=False)
    findings = []
    for kind, value in (("EMAIL", "mira@example.com"), ("PERSON", "Mira Vale")):
        start = doc.text.index(value)
        findings.append(Finding(kind, start, start + len(value), value, .99, "test", "test"))
    findings.sort(key=lambda f: f.start)
    redacted, _ = redact(doc.text, findings)
    result = FileResult(filename=source.name, status=Status.CLEARED, document=doc,
                        findings=findings, redacted_text=redacted,
                        sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    target = tmp_path / "sample.layout_redacted.pptx"
    redact_original_pptx(source, result, target)

    before, after = Presentation(source), Presentation(target)
    assert len(before.slides) == len(after.slides) == 1
    assert len(before.slides[0].shapes) == len(after.slides[0].shapes)
    for a, b in zip(before.slides[0].shapes, after.slides[0].shapes):
        assert (a.left, a.top, a.width, a.height) == (b.left, b.top, b.width, b.height)
    assert after.slides[0].shapes[0].text_frame.paragraphs[0].runs[0].text == "Contact [EMAIL_1]"
    assert after.slides[0].shapes[0].text_frame.paragraphs[0].runs[1].text == " today"
    assert after.slides[0].shapes[1].table.cell(1, 0).text == "[PERSON_1]"
    assert before.slides[0].shapes[1].table.cell(1, 0).text == "Mira Vale"

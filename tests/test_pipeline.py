"""End-to-end behaviour on synthetic files: extraction paths, gate statuses, fail-closed handling."""
import pytest

from cadence_pii import gate, pipeline
from cadence_pii.models import Status

FAKE = ("Owner: Miriam T. Achebe (EMP-38104), m.achebe@cadencefg.example, mobile +1 (917) 555-0143. "
        "Rafael E. Duarte (EMP-40944) holds SSN 900-42-7781.")


def text_of(r):
    return r.redacted_text


def test_docx_text_and_table(make_docx):
    p = make_docx([FAKE, "This paragraph contains no personal data."],
                  table=[["Name", "Email"], ["Naomi K. Osadebe", "n.osadebe@cadencefg.example"]])
    r = pipeline.run_file(p)
    assert r.status in (Status.CLEARED, Status.REVIEW_REQUIRED), r.errors
    red = text_of(r)
    for raw in ["Achebe", "EMP-38104", "m.achebe@", "555-0143", "900-42-7781", "Osadebe", "n.osadebe@"]:
        assert raw not in red, raw
    assert "[EMAIL_" in red and "[PERSON_" in red and "[US_SSN_" in red
    assert "no personal data" in red  # context preserved
    assert all(f.locator for f in r.findings)


def test_docx_embedded_image_is_ocrd(make_docx):
    p = make_docx(["See the screenshot below."], image_lines=["Created by: Naomi Osadebe",
                                                               "Contact: n.osadebe@cadencefg.example"])
    r = pipeline.run_file(p)
    red = text_of(r)
    assert "n.osadebe@" not in red
    assert any(b.kind == "image_ocr" for b in r.document.blocks)
    assert r.status == Status.REVIEW_REQUIRED  # images with PII always need a human look


def test_pptx(make_pptx):
    p = make_pptx([("Directory", "Marguerite Vossberg | m.vossberg@cadencefg.example | +1 (555) 0114")])
    r = pipeline.run_file(p)
    assert r.status == Status.CLEARED, r.reasons
    for raw in ["Vossberg", "m.vossberg@", "0114"]:
        assert raw not in text_of(r)
    assert gate.get_clean_text(r) == r.redacted_text


def test_scanned_pdf_ocr(make_scanned_pdf):
    p = make_scanned_pdf(["Policy owner: Miriam T. Achebe (EMP-38104)", "Email: m.achebe@cadencefg.example",
                          "Phone: +1 (212) 555-0147"])
    r = pipeline.run_file(p)
    assert r.status != Status.ERROR, r.errors
    red = text_of(r)
    assert "EMP-38104" not in red and "m.achebe@" not in red and "555-0147" not in red
    assert "tesseract" in r.document.alt_views


def test_no_pii_document_is_cleared(make_docx):
    r = pipeline.run_file(make_docx(["The committee meets quarterly to review the risk register."]))
    assert r.status == Status.CLEARED and r.findings == []


@pytest.mark.parametrize("name,content", [("empty.docx", b""), ("broken.docx", b"PK\x03\x04garbage"),
                                          ("notes.txt", b"hello"), ("fake.pdf", b"not a pdf")])
def test_bad_inputs_are_errors(tmp_path, name, content):
    p = tmp_path / name
    p.write_bytes(content)
    r = pipeline.run_file(p)
    assert r.status == Status.ERROR and r.errors and r.redacted_text == ""
    with pytest.raises(gate.ReleaseBlocked):
        gate.get_clean_text(r)


def test_detector_failure_fails_closed(make_docx, monkeypatch):
    import cadence_pii.detect.presidio_det as pd

    def boom(*a, **k):
        raise RuntimeError("model crashed")
    monkeypatch.setattr(pd, "detect_presidio", boom)
    r = pipeline.run_file(make_docx([FAKE]))
    assert r.status == Status.ERROR and "Presidio failed" in " ".join(r.errors)
    assert r.redacted_text == ""


def test_batch_continues_after_bad_file(tmp_path, make_docx):
    bad = tmp_path / "bad.pptx"
    bad.write_bytes(b"junk")
    res = pipeline.run_batch([bad, make_docx([FAKE])], progress=lambda *_: None)
    assert [r.status == Status.ERROR for r in res] == [True, False]


def test_review_gate_and_signoff(make_docx):
    r = pipeline.run_file(make_docx(["Screenshot:"], image_lines=["User: Naomi Osadebe"]))
    assert r.status == Status.REVIEW_REQUIRED
    with pytest.raises(gate.ReleaseBlocked):
        gate.get_clean_text(r)
    with pytest.raises(ValueError):
        gate.approve(r, "", "")
    gate.approve(r, "Reviewer A", "Checked screenshot; names masked")
    assert r.status == Status.CLEARED and r.review_log
    assert gate.get_clean_text(r)


def test_blocked_cannot_be_approved(make_docx):
    r = pipeline.run_file(make_docx([FAKE]))
    r.status = Status.BLOCKED
    with pytest.raises(gate.ReleaseBlocked):
        gate.approve(r, "Reviewer A", "override")


def test_reports_never_contain_raw_values(make_docx, tmp_path):
    import json
    from cadence_pii.report import export
    r = pipeline.run_file(make_docx([FAKE]))
    out = export([r], tmp_path / "out")
    blob = (out / "audit_report.json").read_text() + (out / "findings.csv").read_text() + \
        (out / "summary.html").read_text()
    for raw in ["Achebe", "EMP-38104", "m.achebe@", "555-0143", "900-42-7781"]:
        assert raw not in blob, raw
    assert json.loads((out / "audit_report.json").read_text())["files"][0]["status"] == r.status.value

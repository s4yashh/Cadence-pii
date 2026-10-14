"""Preserve Word layout while replacing PII in editable paragraphs and cells.

PRIVATE REVIEW ONLY: embedded screenshots, vector art, textboxes and metadata
are not redacted by python-docx and may still expose PII.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .detect.run import detect_text, finalize
from .layout_pptx import _replace_paragraph
from .models import FileResult, Status
from .redact import _norm


def _paragraphs(document):
    seen = set()

    def table_paragraphs(table):
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    yield paragraph
                for nested in cell.tables:
                    yield from table_paragraphs(nested)

    for paragraph in document.paragraphs:
        if id(paragraph._p) not in seen:
            seen.add(id(paragraph._p))
            yield paragraph
    for table in document.tables:
        for paragraph in table_paragraphs(table):
            if id(paragraph._p) not in seen:
                seen.add(id(paragraph._p))
                yield paragraph
    for section in document.sections:
        for part in (section.header, section.footer):
            for paragraph in part.paragraphs:
                if id(paragraph._p) not in seen:
                    seen.add(id(paragraph._p))
                    yield paragraph
            for table in part.tables:
                for paragraph in table_paragraphs(table):
                    if id(paragraph._p) not in seen:
                        seen.add(id(paragraph._p))
                        yield paragraph


def redact_original_docx(source: Path, result: FileResult, target: Path) -> dict:
    """Create a layout-preserving Word review draft, never overwriting the source."""
    from docx import Document

    source, target = Path(source), Path(target)
    if source.suffix.lower() != ".docx" or source.name != result.filename:
        raise ValueError("source must be the analysed Word file")
    if source.resolve() == target.resolve() or target.exists():
        raise FileExistsError("choose a new output path; the original is never overwritten")
    if result.status not in (Status.CLEARED, Status.REVIEW_REQUIRED):
        raise ValueError(f"cannot create layout review for {result.status.value}")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if result.sha256 not in ("", "cached", digest):
        raise ValueError("source Word file differs from the analysed file")
    document = Document(source)
    mapping, counters, values, changed = {}, {}, set(), 0
    # Docling can merge several names in one Word table cell into a single
    # PERSON finding. Map those lines back onto the original cell paragraphs
    # before running the ordinary paragraph-level recognizers.
    person_values = [re.sub(r"\s+", " ", f.value).strip().lower() for f in result.findings
                     if f.entity_type == "PERSON" and f.start >= 0 and result.document
                     and (block := result.document.block_at(f.start)) and block.kind != "image_ocr"]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    lines = [line.strip() for line in paragraph.text.splitlines() if line.strip()]
                    names = [line for line in lines if len(line) >= 6 and len(line.split()) >= 2
                             and any(line.lower() in value for value in person_values)]
                    if not names:
                        continue
                    replacements = {}
                    for name in names:
                        key = ("PERSON", _norm("PERSON", name))
                        if key not in mapping:
                            counters["PERSON"] = counters.get("PERSON", 0) + 1
                            mapping[key] = f"[PERSON_{counters['PERSON']}]"
                        replacements[name] = mapping[key]
                        values.add(name)
                    pattern = re.compile("|".join(re.escape(v) for v in sorted(replacements, key=len,
                                                                                  reverse=True)))
                    changed += _replace_paragraph(paragraph, pattern, replacements)
    for paragraph in _paragraphs(document):
        text = paragraph.text
        if not text.strip():
            continue
        findings = finalize(detect_text(text), text)
        if not findings:
            continue
        replacements = {}
        for finding in findings:
            key = (finding.entity_type, _norm(finding.entity_type, finding.value))
            if key not in mapping:
                counters[finding.entity_type] = counters.get(finding.entity_type, 0) + 1
                mapping[key] = f"[{finding.entity_type}_{counters[finding.entity_type]}]"
            replacements[finding.value] = mapping[key]
            values.add(finding.value)
        pattern = re.compile("|".join(re.escape(v) for v in sorted(replacements, key=len, reverse=True)))
        changed += _replace_paragraph(paragraph, pattern, replacements)
    if not changed:
        raise ValueError("no editable Word text was replaced")
    target.parent.mkdir(parents=True, exist_ok=True)
    document.save(target)
    check = Document(target)
    remaining = "\n".join(p.text for p in _paragraphs(check))
    if any(value in remaining for value in values):
        target.unlink(missing_ok=True)
        raise ValueError("known PII remained in editable Word text")
    image_findings = sum(1 for f in result.findings if f.start >= 0 and result.document
                         and (block := result.document.block_at(f.start)) and block.kind == "image_ocr")
    return {"editable_replacements": changed, "known_image_findings_not_redacted": image_findings,
            "warning": "Embedded images, vector art, textboxes and metadata may still contain PII"}

"""Preserve an original PowerPoint's layout while masking detected editable text.

This is a PRIVATE REVIEW COPY, not an AI-ready artifact. Source pictures,
animations, metadata, and other non-editable content remain in the package.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .models import FileResult, Status


def _text_frames(slide):
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    def walk(shapes):
        for shape in shapes:
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                yield from walk(shape.shapes)
            else:
                yield shape

    for shape in walk(slide.shapes):
        if shape.has_text_frame:
            yield shape.text_frame
        if shape.has_table:
            for row in shape.table.rows:
                for cell in row.cells:
                    yield cell.text_frame
    if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
        yield slide.notes_slide.notes_text_frame


def _replace_paragraph(paragraph, pattern, replacements) -> int:
    old = paragraph.text
    matches = list(pattern.finditer(old))
    if not matches:
        return 0
    runs = list(paragraph.runs)
    if "".join(run.text for run in runs) != old:
        raise ValueError("PII appears in a paragraph with an unsupported line-break structure")
    owners = [i for i, run in enumerate(runs) for _ in run.text]
    pieces = [[] for _ in runs]
    match_by_start = {m.start(): m for m in matches}
    i = 0
    while i < len(old):
        match = match_by_start.get(i)
        if match:
            pieces[owners[i]].append(replacements[match.group()])
            i = match.end()
        else:
            pieces[owners[i]].append(old[i])
            i += 1
    for run, chars in zip(runs, pieces):
        run.text = "".join(chars)
    return len(matches)


def redact_original_pptx(source: Path, result: FileResult, target: Path) -> Path:
    """Edit the original slide package's text only, preserving shapes and design.

    Fails closed when the source differs from the analysed file or when a finding
    exists in an image: neither can be safely handled as editable slide text.
    """
    from pptx import Presentation

    source, target = Path(source), Path(target)
    if source.suffix.lower() != ".pptx" or source.name != result.filename:
        raise ValueError("source must be the analysed PowerPoint")
    if source.resolve() == target.resolve() or target.exists():
        raise FileExistsError("choose a new output path; the original is never overwritten")
    if result.status not in (Status.CLEARED, Status.REVIEW_REQUIRED):
        raise ValueError(f"cannot create layout review for {result.status.value}")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if result.sha256 not in ("", "cached", digest):
        raise ValueError("source PowerPoint differs from the analysed file")
    if any(result.document.block_at(f.start).kind == "image_ocr" for f in result.findings if f.start >= 0):
        raise ValueError("PII was found inside a picture; text-only slide editing is insufficient")
    replacements = {}
    for f in result.findings:
        if not f.value or not f.placeholder:
            raise ValueError("finding has no replaceable value or placeholder")
        if f.value in replacements and replacements[f.value] != f.placeholder:
            raise ValueError("same source value has conflicting placeholders")
        replacements[f.value] = f.placeholder
    if not replacements:
        raise ValueError("no PII findings to replace")
    pattern = re.compile("|".join(re.escape(v) for v in sorted(replacements, key=len, reverse=True)))
    prs = Presentation(str(source))
    original_counts = {value: 0 for value in replacements}
    changed = 0
    for slide in prs.slides:
        for frame in _text_frames(slide):
            for paragraph in frame.paragraphs:
                for match in pattern.finditer(paragraph.text):
                    original_counts[match.group()] += 1
                changed += _replace_paragraph(paragraph, pattern, replacements)
    missing = [value for value, count in original_counts.items() if count == 0]
    if missing:
        raise ValueError(f"{len(missing)} detected PII value(s) could not be located in editable slide text")
    if not changed:
        raise ValueError("no text was replaced")
    # Original shapes, dimensions, images and layout parts stay in the PPTX.
    target.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(target))
    check = Presentation(str(target))
    text = "\n".join(p.text for slide in check.slides for frame in _text_frames(slide)
                     for p in frame.paragraphs)
    if any(value in text for value in replacements):
        target.unlink(missing_ok=True)
        raise ValueError("known PII remained in editable slide text after replacement")
    return target

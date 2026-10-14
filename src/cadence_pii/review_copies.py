"""Text-only, same-extension review copies reconstructed from final redacted text.

These are deliberately NOT edits of the source files: original images, hidden text,
speaker notes and PDF layers could otherwise carry unredacted PII. They are for
private side-by-side review, never an AI-ready or externally shareable artifact.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from .models import FileResult, Status


NOTICE = "REVIEW COPY - reconstructed from extracted text; not approved for sharing or AI"


def _blocks(r: FileResult) -> list[tuple[object, str]]:
    """Redact each source block, then prove the join equals the verified final text."""
    if not r.document or not r.redacted_text:
        raise ValueError("no extracted/redacted text")
    doc = r.document
    findings = sorted(r.findings, key=lambda f: f.start)
    if any(f.start < 0 or not f.placeholder for f in findings):
        raise ValueError("finding cannot be placed safely in a source block")
    by_id = {b.block_id: b for b in doc.blocks}
    result = []
    used = 0
    for start, end, block_id in doc.spans:
        local = []
        cursor = start
        while used < len(findings) and findings[used].start < end:
            f = findings[used]
            if f.start < cursor or f.end > end:
                raise ValueError("overlapping or cross-block finding")
            local.append(doc.text[cursor:f.start])
            local.append(f.placeholder)
            cursor = f.end
            used += 1
        local.append(doc.text[cursor:end])
        result.append((by_id[block_id], "".join(local)))
    if used != len(findings) or "\n\n".join(text for _, text in result) != r.redacted_text:
        raise ValueError("review copy does not match the final verified redacted text")
    return result


def _pdf(path: Path, r: FileResult, blocks: list[tuple[object, str]]) -> None:
    import pymupdf

    pdf = pymupdf.open()
    current_source = None
    page = None
    y = 0.0

    def new_page(source):
        nonlocal page, y
        page = pdf.new_page(width=595, height=842)
        page.insert_text((40, 38), NOTICE, fontsize=8, color=(0.65, 0.1, 0.1))
        page.insert_text((40, 57), f"{r.filename} | {r.status.value} | source page {source}", fontsize=9)
        y = 78.0

    for block, content in blocks:
        source = block.page or "unknown"
        if source != current_source:
            current_source = source
            new_page(source)
        lines = [f"[{block.kind}; {block.locator}]"]
        for raw in content.splitlines() or [""]:
            lines.extend(textwrap.wrap(raw, width=105, break_long_words=True,
                                       replace_whitespace=False, drop_whitespace=False) or [""])
        lines.append("")
        for line in lines:
            if y > 800:
                new_page(f"{source} continued")
            # Built-in PDF fonts have limited glyph coverage; ASCII placeholders and
            # readable context are more important than exact source typography here.
            safe = line.encode("latin-1", "replace").decode("latin-1")
            page.insert_text((40, y), safe, fontsize=8, fontname="cour", color=(0.1, 0.15, 0.2))
            y += 10
    if not page:
        new_page("unknown")
    pdf.save(path)
    pdf.close()


def _docx(path: Path, r: FileResult, blocks: list[tuple[object, str]]) -> None:
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    doc.add_heading("Redacted text - review copy", 0)
    doc.add_paragraph(NOTICE)
    doc.add_paragraph(f"Source: {r.filename} | status: {r.status.value}")
    for block, content in blocks:
        if block.kind == "heading":
            doc.add_heading(content.removeprefix("## "), level=2)
        else:
            p = doc.add_paragraph()
            p.add_run(f"[{block.locator}] ").bold = True
            p.add_run(content)
            if block.kind in {"table", "image_ocr"}:
                for run in p.runs:
                    run.font.size = Pt(9)
    doc.save(path)


def _pptx(path: Path, r: FileResult, blocks: list[tuple[object, str]]) -> None:
    from pptx import Presentation
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    groups: dict[object, list[str]] = {}
    for block, content in blocks:
        groups.setdefault(block.page or "unknown", []).append(f"[{block.locator}]\n{content}")
    for source, parts in groups.items():
        chunks = []
        current = ""
        for part in parts:
            for piece in textwrap.wrap(part, width=780, break_long_words=True,
                                       replace_whitespace=False, drop_whitespace=False) or [""]:
                if current and len(current) + len(piece) > 1100:
                    chunks.append(current)
                    current = ""
                current += ("\n\n" if current else "") + piece
        if current:
            chunks.append(current)
        for index, content in enumerate(chunks or [""], 1):
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            title = slide.shapes.add_textbox(Inches(.5), Inches(.35), Inches(12.3), Inches(.5))
            title.text_frame.text = f"Source slide {source}" + (f" (part {index})" if len(chunks) > 1 else "")
            title.text_frame.paragraphs[0].font.size = Pt(22)
            box = slide.shapes.add_textbox(Inches(.5), Inches(1.0), Inches(12.3), Inches(5.8))
            box.text_frame.word_wrap = True
            box.text_frame.text = content
            for p in box.text_frame.paragraphs:
                p.font.size = Pt(12)
            footer = slide.shapes.add_textbox(Inches(.5), Inches(7.0), Inches(12.3), Inches(.3))
            footer.text_frame.text = f"{NOTICE} | {r.status.value}"
            footer.text_frame.paragraphs[0].font.size = Pt(8)
    prs.save(path)


def export_review_copy(r: FileResult, outdir: Path) -> Path:
    """Create a same-extension text-only copy; fail closed if redaction mapping disagrees."""
    if r.status not in (Status.CLEARED, Status.REVIEW_REQUIRED):
        raise ValueError(f"cannot create review copy for {r.status.value}")
    blocks = _blocks(r)
    outdir.mkdir(parents=True, exist_ok=True)
    ext = Path(r.filename).suffix.lower()
    target = outdir / f"{Path(r.filename).stem}.review{ext}"
    writers = {".pdf": _pdf, ".docx": _docx, ".pptx": _pptx}
    if ext not in writers:
        raise ValueError(f"unsupported review format: {ext}")
    writers[ext](target, r, blocks)
    return target

"""Visual redaction draft for scanned PDFs, retaining the original page layout.

The output is a raster-only PRIVATE REVIEW COPY. OCR misses and unmatched
findings make it unsuitable for sharing or downstream AI without human review.
"""
from __future__ import annotations

import io
import hashlib
import re
from pathlib import Path

from .detect.run import detect_text, finalize
from .models import FileResult, Status


def _ocr_page(image):
    import pytesseract

    data = pytesseract.image_to_data(image, lang="eng", config="--psm 3",
                                     output_type=pytesseract.Output.DICT)
    words, offsets, chunks = [], [], []
    position = 0
    for i, raw in enumerate(data["text"]):
        word = raw.strip()
        if not word:
            continue
        if chunks:
            chunks.append(" ")
            position += 1
        start = position
        chunks.append(word)
        position += len(word)
        offsets.append((start, position))
        words.append((data["left"][i], data["top"][i],
                      data["width"][i], data["height"][i]))
    return "".join(chunks), offsets, words


def _spans(text: str, result: FileResult, page_number: int):
    spans = []
    matched, unmatched = 0, 0
    for f in result.findings:
        if f.page != page_number or not f.value.strip():
            continue
        matches = list(re.finditer(re.escape(f.value.strip()), text, re.IGNORECASE))
        if matches:
            matched += 1
            spans.extend((m.start(), m.end(), f.placeholder) for m in matches)
        else:
            unmatched += 1
    found = finalize(detect_text(text), text)
    spans.extend((f.start, f.end, f.placeholder or f"[{f.entity_type}]") for f in found)
    # Prefer the longest span when detectors disagree about a boundary.
    spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    kept = []
    for span in spans:
        if not kept or span[0] >= kept[-1][1]:
            kept.append(span)
        elif span[1] > kept[-1][1] and span[0] == kept[-1][0]:
            kept[-1] = span
    return kept, matched, unmatched


def _paint(image, offsets, words, spans):
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 16)
    except OSError:
        font = ImageFont.load_default(size=16)
    painted = 0
    for start, end, label in spans:
        boxes = [box for (a, b), box in zip(offsets, words) if a < end and start < b]
        if not boxes:
            continue
        left = min(x for x, _, _, _ in boxes)
        top = min(y for _, y, _, _ in boxes)
        right = max(x + w for x, _, w, _ in boxes)
        bottom = max(y + h for _, y, _, h in boxes)
        label_width = draw.textbbox((0, 0), label, font=font)[2]
        # Extend the opaque region if the typed tag is longer than the source.
        # This can cover a little neighbouring context and must be reviewed.
        draw.rectangle((left - 2, top - 2, max(right, left + label_width) + 2, bottom + 2), fill="white")
        draw.text((left, top), label, fill=(0, 42, 79), font=font)
        painted += 1
    return painted


def redact_scanned_pdf_for_review(source: Path, result: FileResult, target: Path) -> dict:
    """Render original pages, mask OCR-located PII pixels, return review statistics.

    Output page sizes and visual layout match the source; all source PDF objects
    are replaced with newly rasterised, painted pages to avoid hidden raw layers.
    This is NOT a complete or independently verified redaction.
    """
    import pymupdf
    from PIL import Image

    source, target = Path(source), Path(target)
    if source.suffix.lower() != ".pdf" or source.name != result.filename:
        raise ValueError("source must be the analysed PDF")
    if source.resolve() == target.resolve() or target.exists():
        raise FileExistsError("choose a new output path; the original is never overwritten")
    if result.status not in (Status.CLEARED, Status.REVIEW_REQUIRED):
        raise ValueError(f"cannot create layout review for {result.status.value}")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if result.sha256 not in ("", "cached", digest):
        raise ValueError("source PDF differs from the analysed file")
    original = pymupdf.open(source)
    output = pymupdf.open()
    stats = {"pages": len(original), "painted_regions": 0, "source_findings_matched": 0,
             "source_findings_unmatched": 0, "pages_without_ocr_words": []}
    try:
        for index, page in enumerate(original):
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            text, offsets, words = _ocr_page(image)
            if not words:
                stats["pages_without_ocr_words"].append(index + 1)
            spans, matched, unmatched = _spans(text, result, index + 1)
            stats["source_findings_matched"] += matched
            stats["source_findings_unmatched"] += unmatched
            stats["painted_regions"] += _paint(image, offsets, words, spans)
            stream = io.BytesIO()
            image.save(stream, format="PNG")
            new_page = output.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, stream=stream.getvalue())
        output.set_metadata({"title": "PRIVATE REVIEW COPY - OCR visual redaction draft",
                             "subject": "Not approved for sharing or AI; inspect against original"})
        target.parent.mkdir(parents=True, exist_ok=True)
        output.save(target)
    finally:
        output.close()
        original.close()
    return stats

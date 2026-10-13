"""Choose the extraction strategy per file type and attach secondary views."""
from __future__ import annotations

import time
from pathlib import Path

from ..config import DEFAULT, Settings
from ..models import Document


# Per-format strategy chosen from measurements on the supplied artifacts (docs/file_structure_analysis.md):
# * PDF  - image-only scan: Docling layout/table models + forced Tesseract OCR (+ figure OCR)
# * DOCX - Docling keeps headings/lists/tables (98.5% structure retention); screenshots OCR'd separately
# * PPTX - python-pptx walk of the shape tree keeps each org-chart card (name, title, e-mail, phone)
#          together; Docling regroups them row-wise and loses that association
STRATEGY = {".pdf": ("docling", "native"), ".docx": ("docling", "native"), ".pptx": ("native", "docling")}


def _run(name: str, path: Path, settings: Settings) -> Document:
    if name == "docling":
        from .docling_ext import extract_docling
        return extract_docling(path, settings)
    from .native_ext import extract_native
    return extract_native(path, settings)


def extract(path, settings: Settings = DEFAULT) -> Document:
    """Primary extractor per STRATEGY; on failure fall back to the other one (and say so).

    For PDFs an independent full-resolution Tesseract reading is attached as `alt_views['tesseract']`
    together with per-page confidence and low-confidence-region warnings.
    """
    path = Path(path)
    t0 = time.time()
    primary, fallback = STRATEGY[path.suffix.lower()]
    try:
        doc = _run(primary, path, settings)
        doc.inventory["extractor"] = primary
    except Exception as e:  # fail over, but record it; the gate will require review
        doc = _run(fallback, path, settings)
        doc.inventory["extractor"] = f"{fallback} (fallback)"
        doc.warn(f"{primary} extractor failed ({type(e).__name__}); used {fallback} fallback")
    doc.inventory["extract_secs"] = round(time.time() - t0, 1)

    if path.suffix.lower() == ".pdf" and settings.pdf_dual_ocr and doc.inventory.get("extractor") == "docling":
        from .pdf_ocr import extract_pdf_tesseract
        t1 = time.time()
        tv = extract_pdf_tesseract(path, settings)
        doc.alt_views["tesseract"] = tv.text
        doc.warnings.extend(tv.warnings)
        doc.inventory["ocr_page_conf"] = tv.inventory.get("ocr_page_conf")
        doc.inventory["text_layer_pages"] = tv.inventory.get("text_layer_pages")
        doc.inventory["second_ocr_secs"] = round(time.time() - t1, 1)
        # Docling should not have dropped whole pages: compare page coverage
        docling_pages = {b.page for b in doc.blocks if b.page}
        missing = sorted(set(range(1, (tv.inventory.get("pages_or_slides") or 0) + 1)) - docling_pages)
        if missing:
            doc.warn(f"Docling produced no text for pages {missing}")

    if not doc.text.strip():
        doc.warn("extraction produced no text")
    else:
        _coverage_check(path, doc)
    return doc


def _ooxml_text_chars(path: Path) -> int:
    """Non-whitespace characters in the OOXML text runs (w:t / a:t) - a cheap completeness reference."""
    import re
    import zipfile
    n = 0
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.endswith(".xml") and name.startswith(("word/document", "word/header", "word/footer",
                                                          "word/footnotes", "ppt/slides/slide", "ppt/notesSlides/")):
                xml = z.read(name).decode("utf8", "ignore")
                runs = re.findall(r"<(?:w|a):t(?:\s[^>]*)?>([^<]*)</(?:w|a):t>", xml)
                n += sum(1 for t in runs for c in t if not c.isspace())
    return n


def _coverage_check(path: Path, doc: Document, min_ratio: float = 0.8) -> None:
    """Flag extraction that silently dropped content (compares like-for-like non-whitespace characters)."""
    ext = path.suffix.lower()
    if ext in (".docx", ".pptx"):
        ref = _ooxml_text_chars(path)
        got = sum(1 for b in doc.blocks if b.kind != "image_ocr" for c in b.text
                  if not c.isspace() and c not in "|-#")  # ignore markdown table/heading syntax
        doc.inventory["source_text_chars"] = ref
        doc.inventory["extracted_text_chars"] = got
        doc.inventory["text_coverage"] = round(got / ref, 3) if ref else None
        if ref and got < min_ratio * ref:
            doc.warn(f"extracted text covers only {100 * got / ref:.0f}% of the source text runs")
    elif ext == ".pdf":
        pages = doc.inventory.get("pages_or_slides") or 0
        per_page = {}
        for b in doc.blocks:
            if b.page:
                per_page[b.page] = per_page.get(b.page, 0) + len(b.text)
        thin = [p for p in range(1, pages + 1) if per_page.get(p, 0) < 40]
        if thin:
            doc.warn(f"pages with almost no extracted text: {thin}")

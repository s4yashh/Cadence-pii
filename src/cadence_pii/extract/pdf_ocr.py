"""Independent full-resolution Tesseract view of a PDF.

Used (a) to measure per-page OCR confidence and find low-confidence regions for human review,
(b) as a second OCR reading that the verification step cross-checks against, and
(c) as a fallback extractor if Docling fails. Pages with a usable text layer use that layer instead.
"""
from __future__ import annotations

import io
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymupdf
from PIL import Image

from ..config import DEFAULT, Settings
from ..models import Block, Document
from .image_ocr import ocr_image


def _page_image(doc, page) -> Image.Image:
    imgs = page.get_images(full=True)
    if len(imgs) == 1:  # scanned page: use the embedded raster at native resolution
        data = doc.extract_image(imgs[0][0])["image"]
        return Image.open(io.BytesIO(data))
    pix = page.get_pixmap(dpi=200)
    return Image.open(io.BytesIO(pix.tobytes("png")))


def extract_pdf_tesseract(path, settings: Settings = DEFAULT) -> Document:
    path = Path(path)
    out = Document(filename=path.name, filetype="pdf")
    with pymupdf.open(path) as pdf:
        n = pdf.page_count
        native = [pdf[i].get_text("text").strip() for i in range(n)]
        images = [None if len(native[i]) > 50 else _page_image(pdf, pdf[i]) for i in range(n)]

    def work(i):
        if images[i] is None:
            return i, native[i], None
        return i, None, ocr_image(images[i], settings.ocr_lang, settings.ocr_min_block_conf,
                                  settings.ocr_min_words_for_conf)

    with ThreadPoolExecutor(max_workers=max(1, (os.cpu_count() or 2))) as ex:
        results = sorted(ex.map(work, range(n)))
    page_conf = {}
    for i, txt, r in results:
        p = i + 1
        if r is None:
            out.blocks.append(Block(p, f"page {p} / text layer", "paragraph", txt, "native", p))
            continue
        page_conf[p] = r.mean_conf
        out.blocks.append(Block(p, f"page {p} / OCR", "page_ocr", r.text, "tesseract", p, r.mean_conf, r.n_words))
        if not r.text.strip():
            out.warn(f"page {p}: OCR produced no text")
        for (bnum, conf, nw) in r.low_conf_regions:
            out.warn(f"page {p}: low-confidence OCR region (block {bnum}, mean conf {conf}, {nw} words)")
    out.inventory.update({"pages_or_slides": n, "text_layer_pages": sum(1 for t in native if len(t) > 50),
                          "ocr_page_conf": page_conf})
    out.assemble()
    return out

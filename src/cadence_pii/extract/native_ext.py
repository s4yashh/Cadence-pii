"""Reference / fallback extractor using python-docx and python-pptx directly.

Serves two purposes:
1. Structure-retention baseline: the OOXML parse is ground truth for what text elements exist.
2. Fallback when Docling fails, so a document is never silently skipped.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from ..config import DEFAULT, Settings
from ..models import Block, Document
from .image_ocr import ocr_image

RASTER = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff")


def _table_md(rows) -> str:
    rows = [[c.replace("\n", " ").replace("|", "/").strip() for c in r] for r in rows if any(c.strip() for c in r)]
    if not rows:
        return ""
    w = max(len(r) for r in rows)
    rows = [r + [""] * (w - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * w]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def _docx(path: Path, ocr: bool, settings: Settings) -> Document:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(str(path))
    doc = Document(filename=path.name, filetype="docx")
    bid, section = 0, "start"
    for el in d.element.body.iterchildren():
        tag = el.tag.split("}")[-1]
        if tag == "p":
            p = Paragraph(el, d)
            t = p.text.strip()
            if not t:
                continue
            style = (p.style.name or "").lower() if p.style is not None else ""
            kind = "heading" if style.startswith(("heading", "title")) else (
                "list_item" if "list" in style or el.find(".//{*}numPr") is not None else "paragraph")
            if kind == "heading":
                section = t
            bid += 1
            doc.blocks.append(Block(bid, f"section '{section[:60]}' / {kind}", kind, t, "native"))
        elif tag == "tbl":
            tb = Table(el, d)
            md = _table_md([[c.text for c in r.cells] for r in tb.rows])
            if md:
                bid += 1
                doc.blocks.append(Block(bid, f"section '{section[:60]}' / table", "table", md, "native"))
    for i, s in enumerate(d.sections):
        for part, name in ((s.header, "header"), (s.footer, "footer")):
            t = "\n".join(p.text for p in part.paragraphs if p.text.strip())
            if t:
                bid += 1
                doc.blocks.append(Block(bid, f"section {i+1} {name}", "furniture", t, "native"))
    if ocr:
        with zipfile.ZipFile(path) as z:
            for n in sorted(x for x in z.namelist() if x.startswith("word/media/")):
                if n.lower().endswith(RASTER):
                    r = ocr_image(z.read(n), settings.ocr_lang)
                    if r.text:
                        bid += 1
                        doc.blocks.append(Block(bid, f"embedded image {n.split('/')[-1]}", "image_ocr",
                                                r.text, "tesseract", None, r.mean_conf, r.n_words))
                else:
                    doc.warn(f"embedded image {n.split('/')[-1]} is not a raster format - not OCR'd")
    doc.assemble()
    return doc


def _pptx(path: Path, ocr: bool, settings: Settings) -> Document:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    prs = Presentation(str(path))
    doc = Document(filename=path.name, filetype="pptx")
    bid = 0

    def walk(shapes):
        for sh in shapes:
            if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
                yield from walk(sh.shapes)
            else:
                yield sh

    for sno, slide in enumerate(prs.slides, 1):
        for sh in walk(slide.shapes):
            if sh.has_text_frame and sh.text_frame.text.strip():
                for para in sh.text_frame.paragraphs:
                    t = "".join(r.text for r in para.runs).strip()
                    if t:
                        bid += 1
                        doc.blocks.append(Block(bid, f"slide {sno} / shape '{sh.name}'", "paragraph", t, "native", sno))
            elif getattr(sh, "has_table", False) and sh.has_table:
                md = _table_md([[c.text for c in r.cells] for r in sh.table.rows])
                bid += 1
                doc.blocks.append(Block(bid, f"slide {sno} / table '{sh.name}'", "table", md, "native", sno))
            elif ocr and sh.shape_type == MSO_SHAPE_TYPE.PICTURE:
                try:
                    blob = sh.image.blob
                except Exception:
                    doc.warn(f"slide {sno}: picture '{sh.name}' could not be read - not OCR'd")
                    continue
                r = ocr_image(blob, settings.ocr_lang)
                if r.text:
                    bid += 1
                    doc.blocks.append(Block(bid, f"slide {sno} / image '{sh.name}'", "image_ocr", r.text,
                                            "tesseract", sno, r.mean_conf, r.n_words))
        if slide.has_notes_slide:
            t = slide.notes_slide.notes_text_frame.text.strip() if slide.notes_slide.notes_text_frame else ""
            if t:
                bid += 1
                doc.blocks.append(Block(bid, f"slide {sno} / speaker notes", "notes", t, "native", sno))
    doc.inventory["pages_or_slides"] = len(prs.slides)
    doc.inventory["tables"] = sum(1 for b in doc.blocks if b.kind == "table")
    doc.inventory["pictures"] = sum(1 for b in doc.blocks if b.kind == "image_ocr")
    doc.assemble()
    return doc


def extract_native(path, settings: Settings = DEFAULT, ocr: bool = True) -> Document:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".docx":
        return _docx(path, ocr, settings)
    if ext == ".pptx":
        return _pptx(path, ocr, settings)
    if ext == ".pdf":
        from .pdf_ocr import extract_pdf_tesseract
        return extract_pdf_tesseract(path, settings)
    raise ValueError(f"unsupported: {ext}")

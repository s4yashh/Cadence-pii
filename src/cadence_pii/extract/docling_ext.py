"""Primary extractor: Docling (layout-aware) for PDF, DOCX and PPTX.

* PDF  -> Docling layout + table-structure models with forced full-page Tesseract OCR (the
          supplied PDF is image-only, so OCR is mandatory). Text inside figures (photos of forms,
          diagrams) is not part of Docling's text output, so each figure crop is OCR'd as well.
* DOCX -> Docling's native OOXML backend. Embedded pictures are OCR'd here with Tesseract,
          because Docling does not OCR images inside Word files.
* PPTX -> Docling's native backend (slides, tables, speaker notes); pictures OCR'd likewise.
Docling's remote services stay disabled (default), so nothing leaves the runtime.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ..config import DEFAULT, Settings
from ..models import Block, Document
from .image_ocr import ocr_image

LABEL_KIND = {
    "title": "heading", "section_header": "heading", "text": "paragraph", "paragraph": "paragraph",
    "list_item": "list_item", "caption": "caption", "footnote": "paragraph", "table": "table",
    "page_header": "furniture", "page_footer": "furniture", "code": "paragraph", "formula": "paragraph",
    "picture": "picture", "chart": "picture", "document_index": "table", "reference": "paragraph",
    "key_value_region": "paragraph", "form": "paragraph", "handwritten_text": "paragraph",
}


def _inside_table(item, d) -> bool:
    """Rich table cells are yielded again as standalone items; they are already in the table text."""
    from docling_core.types.doc import TableItem
    ref = getattr(item, "parent", None)
    while ref is not None:
        node = ref.resolve(d)
        if isinstance(node, TableItem):
            return True
        ref = getattr(node, "parent", None)
    return False


def _native_crop(path: Path, item, d, pad: int = 8):
    """Crop a PDF figure from the page's native-resolution raster (sharper than Docling's render)."""
    try:
        import io

        import pymupdf
        from PIL import Image
        prov = item.prov[0]
        page_no, bb = prov.page_no, prov.bbox
        size = d.pages[page_no].size
        with pymupdf.open(path) as pdf:
            pg = pdf[page_no - 1]
            imgs = pg.get_images(full=True)
            if len(imgs) != 1:
                return None
            img = Image.open(io.BytesIO(pdf.extract_image(imgs[0][0])["image"]))
            # where the raster sits on the page (points)
            r = pg.get_image_rects(imgs[0][0])[0]
        bb = bb.to_top_left_origin(page_height=size.height)
        sx, sy = img.width / r.width, img.height / r.height
        box = (max(0, int((bb.l - r.x0) * sx) - pad), max(0, int((bb.t - r.y0) * sy) - pad),
               min(img.width, int((bb.r - r.x0) * sx) + pad), min(img.height, int((bb.b - r.y0) * sy) + pad))
        if box[2] - box[0] < 20 or box[3] - box[1] < 20:
            return None
        return img.crop(box)
    except Exception:
        return None


@lru_cache(maxsize=2)
def _converter(ocr_lang: str):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        ocr_options=TesseractCliOcrOptions(force_full_page_ocr=True, lang=[ocr_lang]),
        generate_picture_images=True,  # figure crops are OCR'd separately (Docling omits text inside figures)
        images_scale=2.0,
    )
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})


def extract_docling(path, settings: Settings = DEFAULT) -> Document:
    from docling_core.types.doc import ContentLayer, PictureItem, TableItem

    path = Path(path)
    ext = path.suffix.lower().lstrip(".")
    res = _converter(settings.ocr_lang).convert(str(path), raises_on_error=False)
    if str(res.status).split(".")[-1] not in ("SUCCESS", "PARTIAL_SUCCESS"):
        raise RuntimeError(f"Docling conversion status {res.status}: {[str(e) for e in res.errors][:3]}")
    d = res.document
    doc = Document(filename=path.name, filetype=ext)
    if str(res.status).endswith("PARTIAL_SUCCESS"):
        doc.warn("Docling reported PARTIAL_SUCCESS (some pages/elements not converted)")

    unit = {"pdf": "page", "pptx": "slide"}.get(ext)
    layers = {ContentLayer.BODY, ContentLayer.FURNITURE, ContentLayer.NOTES}
    counters: dict = {}
    section = "start"
    bid = 0
    unsupported_pics = 0
    for item, _lvl in d.iterate_items(included_content_layers=layers):
        if not isinstance(item, PictureItem) and _inside_table(item, d):
            continue
        label = str(getattr(item, "label", "")).split(".")[-1].lower()
        kind = LABEL_KIND.get(label, "paragraph")
        layer = str(getattr(item, "content_layer", "body")).split(".")[-1].lower()
        if layer == "notes":
            kind = "notes"
        elif layer == "furniture" and kind not in ("picture",):
            kind = "furniture"
        page = item.prov[0].page_no if getattr(item, "prov", None) else None
        counters[kind] = counters.get(kind, 0) + 1
        where = f"{unit} {page}" if unit and page else f"section '{section[:60]}'"
        locator = f"{where} / {kind} #{counters[kind]}"

        if isinstance(item, TableItem):
            text = item.export_to_markdown(doc=d)
        elif isinstance(item, PictureItem):
            img = _native_crop(path, item, d) if ext == "pdf" else None
            if img is None:
                img = item.get_image(d)
            if img is None:
                unsupported_pics += 1
                if layer == "furniture":  # header/footer art (logos) - recorded, not blocking
                    doc.warn(f"header/footer picture ({locator}) is vector (EMF/WMF) - not OCR'd", "info")
                else:
                    doc.warn(f"body picture at {locator} is vector (EMF/WMF/SVG) - not OCR'd; check manually")
                continue
            r = ocr_image(img, settings.ocr_lang, settings.ocr_min_block_conf, settings.ocr_min_words_for_conf)
            if not r.text:
                continue
            bid += 1
            doc.blocks.append(Block(bid, locator.replace("picture", "image"), "image_ocr", r.text, "tesseract",
                                    page, r.mean_conf, r.n_words))
            continue
        else:
            text = getattr(item, "text", "") or ""
        if kind == "heading" and text.strip():
            section = text.strip()
        if not text.strip():
            continue
        bid += 1
        doc.blocks.append(Block(bid, locator, kind, text.strip(), "docling", page,
                                None))
    doc.inventory.update({
        "pages_or_slides": len(d.pages) if d.pages else None,
        "tables": len(d.tables),
        "pictures": len(d.pictures),
        "pictures_without_raster": unsupported_pics,
    })
    doc.assemble()
    return doc

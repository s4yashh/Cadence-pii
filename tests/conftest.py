"""Synthetic fixtures only. Every value below is fabricated (555 numbers, example domains, 900-series SSNs)."""
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def text_image(lines, size=(1400, 500), font_size=36):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=font_size)
    y = 30
    for ln in lines:
        d.text((40, y), ln, fill="black", font=font)
        y += font_size + 20
    return img


def png_bytes(img):
    b = io.BytesIO()
    img.save(b, format="PNG")
    return b.getvalue()


@pytest.fixture
def make_docx(tmp_path):
    def _make(paragraphs=(), table=None, image_lines=None, name="sample.docx"):
        import docx
        from docx.shared import Inches
        d = docx.Document()
        d.add_heading("Synthetic test document", level=1)
        for p in paragraphs:
            d.add_paragraph(p)
        if table:
            t = d.add_table(rows=len(table), cols=len(table[0]))
            for i, row in enumerate(table):
                for j, v in enumerate(row):
                    t.cell(i, j).text = v
        if image_lines:
            d.add_picture(io.BytesIO(png_bytes(text_image(image_lines))), width=Inches(6))
        p = tmp_path / name
        d.save(p)
        return p
    return _make


@pytest.fixture
def make_pptx(tmp_path):
    def _make(slides, name="sample.pptx"):
        from pptx import Presentation
        from pptx.util import Inches
        prs = Presentation()
        for title, body in slides:
            s = prs.slides.add_slide(prs.slide_layouts[1])
            s.shapes.title.text = title
            s.placeholders[1].text = body
        p = tmp_path / name
        prs.save(p)
        return p
    return _make


@pytest.fixture
def make_scanned_pdf(tmp_path):
    """A PDF whose only content is a raster image of text (no text layer), like the supplied policy."""
    def _make(lines, name="scan.pdf"):
        import pymupdf
        img = text_image(lines, size=(1654, 900), font_size=40)
        doc = pymupdf.open()
        page = doc.new_page(width=595, height=842)
        page.insert_image(pymupdf.Rect(20, 20, 575, 320), stream=png_bytes(img))
        p = tmp_path / name
        doc.save(p)
        return p
    return _make


@pytest.fixture
def fast_settings():
    from cadence_pii.config import Settings
    return Settings()

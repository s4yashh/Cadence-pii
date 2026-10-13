"""Local Tesseract OCR helpers (no network). Returns text with line structure and confidence."""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import pytesseract
from PIL import Image, ImageOps


@dataclass
class OcrResult:
    text: str
    mean_conf: float          # mean confidence of real words (0-100); 0 when no words
    n_words: int
    low_conf_regions: list = field(default_factory=list)  # [(block_num, mean_conf, n_words)]


def _prep(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
        img = bg
    img = img.convert("L")
    # Small UI screenshots OCR much better when upscaled.
    if img.width < 1200:
        f = min(3.0, 1600 / max(img.width, 1))
        img = img.resize((int(img.width * f), int(img.height * f)), Image.LANCZOS)
    return img


def ocr_image(img, lang: str = "eng", region_min_conf: float = 60.0, region_min_words: int = 5) -> OcrResult:
    """OCR a PIL image or raw bytes; rebuild lines/paragraphs from Tesseract's layout tree."""
    if isinstance(img, (bytes, bytearray)):
        img = Image.open(io.BytesIO(img))
    img = _prep(img)
    d = pytesseract.image_to_data(img, lang=lang, config="--psm 3", output_type=pytesseract.Output.DICT)
    lines: dict = {}
    blocks: dict = {}
    confs = []
    for i, w in enumerate(d["text"]):
        w = w.strip()
        c = float(d["conf"][i])
        if not w or c < 0:
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        lines.setdefault(key, []).append(w)
        blocks.setdefault(d["block_num"][i], []).append(c)
        confs.append(c)
    out, prev = [], None
    for key in sorted(lines):
        if prev is not None and key[:2] != prev[:2]:
            out.append("")  # blank line between paragraphs
        out.append(" ".join(lines[key]))
        prev = key
    low = [(b, round(sum(c) / len(c), 1), len(c)) for b, c in blocks.items()
           if len(c) >= region_min_words and sum(c) / len(c) < region_min_conf]
    return OcrResult("\n".join(out).strip(), round(sum(confs) / len(confs), 1) if confs else 0.0, len(confs), low)

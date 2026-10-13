"""Deterministic, fresh synthetic text/table/screenshot challenge set.

This is a small out-of-sample smoke test, not an estimate of population accuracy.
No generated raw values are written to disk.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from faker import Faker
from PIL import Image, ImageDraw, ImageFont

from cadence_pii.detect.run import detect_document
from cadence_pii.evaluate import evaluate_file, save_sanitized
from cadence_pii.extract.image_ocr import ocr_image
from cadence_pii.models import Block, Document, FileResult
from cadence_pii.redact import redact


def main() -> None:
    fake = Faker("en_US")
    Faker.seed(20261013)
    blocks, regions = [], []
    for i in range(12):
        name = fake.name()
        email = name.lower().replace(" ", ".").replace("'", "") + "@example.test"
        employee = f"EMP-{39000 + i}"
        phone = f"+1 (415) 555-{2000 + i:04d}"
        if i % 3 == 0:
            content = f"Review owner: {name}. Contact: {email}. Direct: {phone}. Badge: {employee}."
            kind = "paragraph"
        elif i % 3 == 1:
            content = f"| Owner | Contact | Badge | Phone |\n|---|---|---|---|\n| {name} | {email} | {employee} | {phone} |"
            kind = "table"
        else:
            content = f"Escalation for {name}: email {email}; employee ID {employee}; phone {phone}."
            kind = "paragraph"
        blocks.append(Block(i, f"synthetic case {i+1}", kind, content, "synthetic", page=i+1))
        regions.append({"id": f"case-{i+1}", "selector": {"page": i+1},
                        "items": [["PERSON", name], ["EMAIL", email], ["EMPLOYEE_ID", employee], ["PHONE", phone]]})

    # Screenshot challenge: compare OCR text to the known source text before measuring detection.
    screenshot_name = fake.name()
    screenshot_email = f"{screenshot_name.lower().replace(' ', '.')}@example.test"
    screenshot_lines = ["User management", f"User: {screenshot_name}", f"Email: {screenshot_email}"]
    img = Image.new("RGB", (1100, 260), "white")
    draw = ImageDraw.Draw(img)
    font_path = "/System/Library/Fonts/Supplemental/Arial.ttf"
    font = ImageFont.truetype(font_path, 34) if Path(font_path).exists() else ImageFont.load_default()
    for j, line in enumerate(screenshot_lines):
        draw.text((28, 25 + j * 72), line, fill="black", font=font)
    ocr = ocr_image(img)
    blocks.append(Block(12, "synthetic screenshot", "image_ocr", ocr.text, "tesseract",
                        page=13, ocr_conf=ocr.mean_conf, ocr_words=ocr.n_words))
    ocr_found = {"name": screenshot_name in ocr.text, "email": screenshot_email in ocr.text}
    regions.append({"id": "screenshot", "selector": {"page": 13},
                    "items": [["PERSON", screenshot_name], ["EMAIL", screenshot_email]]})

    doc = Document("heldout-synthetic", ".txt", blocks=blocks)
    doc.assemble()
    result = FileResult(doc.filename, document=doc)
    result.findings = detect_document(doc)
    result.redacted_text, _ = redact(doc.text, result.findings)
    measured = evaluate_file(result, {"file": doc.filename, "regions": regions})
    measured["challenge"] = {"seed": 20261013, "cases": 12, "screenshots": 1,
                             "screenshot_ocr_confidence": ocr.mean_conf,
                             "screenshot_source_values_in_ocr": ocr_found,
                             "scope": "synthetic generated text/table and one rendered screenshot; detection only"}
    out = ROOT / "evaluation" / "results"
    out.mkdir(parents=True, exist_ok=True)
    save_sanitized(measured, out / "heldout_synthetic.json")
    print(measured["summary"])
    print("screenshot source values found by OCR:", ocr_found)
    print("gold selector/value errors:", len(measured["gold_errors"]))


if __name__ == "__main__":
    main()

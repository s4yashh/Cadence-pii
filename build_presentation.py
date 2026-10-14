"""Generate the eight-slide, editable Cadence technical-review deck."""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "Optiv_Case_Study_2_Presentation.pptx"
P = Presentation()
P.slide_width, P.slide_height = Inches(13.333), Inches(7.5)
NAVY = RGBColor(22, 35, 54)
INK = RGBColor(57, 69, 84)
BLUE = RGBColor(40, 100, 169)
MUTED = RGBColor(105, 119, 135)
RULE = RGBColor(211, 220, 229)
PALE = RGBColor(246, 249, 252)
WHITE = RGBColor(255, 255, 255)


def txt(s, value, x, y, w, h, size=15, color=INK, bold=False,
        align=PP_ALIGN.LEFT, valign=MSO_ANCHOR.MIDDLE):
    box = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Inches(0)
    tf.vertical_anchor = valign
    for i, line in enumerate(value.split("\n")):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.text = line
        para.alignment = align
        para.space_before = para.space_after = Pt(0)
        para.font.name = "Aptos"
        para.font.size = Pt(size)
        para.font.bold = bold
        para.font.color.rgb = color
    return box


def rect(s, x, y, w, h, fill=WHITE, stroke=RULE, stroke_width=1):
    sh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if stroke is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = stroke
        sh.line.width = Pt(stroke_width)
    return sh


def link(s, x1, y1, x2, y2, color=BLUE, arrow=False, width=1):
    sh = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    sh.line.color.rgb = color
    sh.line.width = Pt(width)
    if arrow:
        end = OxmlElement("a:tailEnd")
        end.set("type", "triangle")
        end.set("w", "sm")
        end.set("len", "sm")
        sh._element.spPr.get_or_add_ln().append(end)
    return sh


def page(title, section):
    s = P.slides.add_slide(P.slide_layouts[6])
    rect(s, 0, 0, 13.333, 7.5, WHITE, None)
    txt(s, section.upper(), .68, .28, 11.9, .29, 10, BLUE, True)
    txt(s, title, .68, .67, 12, .68, 27, NAVY, True)
    link(s, .68, 1.48, 12.65, 1.48, RULE)
    link(s, .68, 7.04, 12.65, 7.04, RULE)
    txt(s, "CADENCE  /  OPTIV CASE STUDY 02", .68, 7.12, 9.8, .22, 9, MUTED)
    txt(s, f"{len(P.slides):02d} / 08", 11.6, 7.12, 1.05, .22, 9, MUTED, align=PP_ALIGN.RIGHT)
    return s


def label(s, value, x, y, w):
    txt(s, value.upper(), x, y, w, .28, 10, BLUE, True)
    link(s, x, y + .38, x + w, y + .38, RULE)


def module(s, title, detail, x, y, w, h, accent=False, title_size=14, detail_size=11):
    rect(s, x, y, w, h, PALE if accent else WHITE, BLUE if accent else RULE, 1.2 if accent else 1)
    txt(s, title, x + .12, y + .10, w - .24, .33, title_size, NAVY, True)
    txt(s, detail, x + .12, y + .50, w - .24, h - .57, detail_size, INK,
        valign=MSO_ANCHOR.TOP)


# 1 — Title
s = P.slides.add_slide(P.slide_layouts[6])
rect(s, 0, 0, 13.333, 7.5, WHITE, None)
rect(s, .70, .78, .08, 5.18, BLUE, None)
txt(s, "TECHNICAL CASE STUDY", 1.04, .84, 8, .36, 12, BLUE, True)
txt(s, "Cadence PII Detection —\nCase Study 02, Engagement with Optiv",
    1.04, 1.52, 11.1, 2.18, 33, NAVY, True, valign=MSO_ANCHOR.TOP)
txt(s, "Extract document text. Classify and redact PII. Verify before AI release.",
    1.05, 4.24, 10.9, .62, 19, INK)
link(s, 1.04, 5.72, 12.27, 5.72, RULE)
txt(s, "PDF  /  DOCX  /  PPTX", 1.04, 6.00, 5, .37, 12, BLUE, True)
txt(s, "Implementation and measured case-study outcomes", 7.00, 6.00, 5.27, .37, 12,
    MUTED, align=PP_ALIGN.RIGHT)


# 2 — Problem and solution
s = page("The problem and the control objective", "Problem and solution")
label(s, "Exposure risk", .70, 1.82, 5.68)
txt(s, "Financial documents combine native text, scans, tables and screenshots.",
    .70, 2.39, 5.57, .70, 19, NAVY, True)
txt(s, "A name or identifier missed during extraction can pass through a text-only filter and reach an AI workflow.",
    .70, 3.23, 5.55, 1.16, 16, INK, valign=MSO_ANCHOR.TOP)
link(s, 6.65, 1.83, 6.65, 4.48, RULE)
label(s, "Designed response", 6.94, 1.82, 5.69)
txt(s, "A document-level release gate—not just a redaction function.",
    6.94, 2.39, 5.55, .70, 19, NAVY, True)
txt(s, "Preserve source locations, detect PII classes, replace values, re-check the output and withhold uncertain files.",
    6.94, 3.23, 5.54, 1.16, 16, INK, valign=MSO_ANCHOR.TOP)
label(s, "High-level workflow", .70, 4.81, 11.93)
for i, name in enumerate(("Upload", "Extract", "Detect", "Redact", "Verify", "Gate")):
    x = .73 + i * 2.02
    txt(s, f"{i+1:02d}", x, 5.44, .38, .40, 11, BLUE, True)
    txt(s, name, x + .42, 5.43, 1.35, .42, 17, NAVY, True)
    if i < 5:
        link(s, x + 1.63, 5.65, x + 1.88, 5.65, BLUE, True)
txt(s, "Scope: redacted extracted text is prepared for downstream AI; original files are not rewritten.",
    .73, 6.30, 11.87, .35, 12, MUTED)


# 3 — Functional design. All nodes and arrows remain editable.
s = page("Functional design: from upload to decision", "Required functional design")
stages = (("Upload", "PDF / DOCX / PPTX"), ("Validate", "Type, size, integrity"),
          ("Extract", "Native text + OCR"), ("Normalize", "Blocks + locators"),
          ("Detect", "PII types + spans"), ("Redact", "Typed placeholders"),
          ("Verify", "Second pass"))
for i, (name, detail) in enumerate(stages):
    x = .67 + i * 1.765
    module(s, name, detail, x, 2.04, 1.55, 1.12, i in (0, 6), 13, 10)
    if i < 6:
        link(s, x + 1.56, 2.58, x + 1.75, 2.58, BLUE, True)
link(s, 11.98, 3.16, 11.98, 3.70, BLUE, True)
module(s, "Release gate", "Final status", 10.91, 3.75, 2.15, .88, True, 14, 11)
link(s, 11.98, 4.63, 11.98, 4.88, RULE)
link(s, 2.26, 4.88, 11.98, 4.88, RULE)
branches = ((2.26, "CLEARED", "Write redacted text to ai_ready"),
            (6.67, "REVIEW_REQUIRED", "Human source review; sign off or withhold"),
            (11.06, "BLOCKED / ERROR", "No AI-ready release"))
for cx, name, detail in branches:
    link(s, cx, 4.88, cx, 5.19, BLUE, True)
    module(s, name, detail, cx - 1.57, 5.23, 3.14, 1.07, name == "CLEARED", 13, 11)
txt(s, "One remediation pass precedes the final gate; any processing error fails closed.",
    .72, 6.55, 11.88, .25, 11, MUTED)


# 4 — System architecture. Editable component boxes and connectors.
s = page("System architecture: modules and interactions", "Required technical architecture")
architecture = (
    ("Colab notebook", "Upload, run, masked\npreview, export ZIP", "build_notebook.py"),
    ("Orchestrator", "validate() + run_batch()\nper-file fail-closed result", "ingest.py / pipeline.py"),
    ("Extraction", "Docling or native parser\nTesseract image OCR", "extract/router.py"),
    ("PII processing", "regex + Presidio / spaCy\nmerge → redact → verify", "detect/ / redact.py / verify.py"),
    ("Release + audit", "gate.decide()\nreport.export()", "gate.py / report.py"),
)
for i, (name, detail, filename) in enumerate(architecture):
    x = .68 + i * 2.42
    rect(s, x, 2.07, 2.24, 3.34, PALE if i in (0, 4) else WHITE,
         BLUE if i in (0, 4) else RULE)
    rect(s, x, 2.07, 2.24, .07, BLUE, None)
    txt(s, name, x + .15, 2.34, 1.94, .58, 16, NAVY, True)
    txt(s, detail, x + .15, 3.11, 1.94, 1.32, 13, INK, valign=MSO_ANCHOR.TOP)
    link(s, x + .15, 4.64, x + 2.09, 4.64, RULE)
    txt(s, filename, x + .15, 4.80, 1.94, .38, 10, BLUE)
    if i < 4:
        link(s, x + 2.25, 3.70, x + 2.40, 3.70, BLUE, True)
txt(s, "Shared data contract: Document = ordered blocks + source locators; Finding = type + character span + detector.",
    .72, 5.74, 11.88, .53, 14, NAVY, True)
txt(s, "Runs in the active Python runtime. No document-content API or downstream LLM call is implemented.",
    .72, 6.34, 11.88, .34, 12, MUTED)


# 5 — Structure analysis and extraction logic
s = page("File structure determines the extraction path", "File structure analysis and extraction logic")
columns = ((.72, 1.58, "FORMAT"), (2.30, 2.90, "OBSERVED STRUCTURE"),
           (5.20, 4.27, "EXTRACTION METHOD"), (9.47, 3.17, "PRESERVATION CHECK"))
rect(s, .70, 1.83, 11.96, .53, PALE, None)
for x, w, name in columns:
    txt(s, name, x + .10, 1.96, w - .18, .22, 10, BLUE, True)
rows = (
    ("PDF", "35 scanned pages; no usable text layer", "Docling layout + full-page Tesseract; OCR figure crops; independent page OCR view", "Heading, table and figure proxies; low-confidence pages flagged"),
    ("PPTX", "9 slides; org-chart shapes and tables", "Native python-pptx shape walk keeps name/contact groupings; picture OCR", "Native OOXML text, table cells, type and order comparison"),
    ("DOCX", "Headings, tables and embedded screenshots", "Docling for Word structure; Tesseract OCR for raster pictures", "Native OOXML text, table cells, type and order comparison"),
)
for i, row in enumerate(rows):
    y = 2.36 + i * 1.33
    link(s, .70, y, 12.66, y, RULE)
    for j, ((x, w, _), value) in enumerate(zip(columns, row)):
        txt(s, value, x + .10, y + .17, w - .20, 1.01, 15 if j == 0 else 13,
            NAVY if j == 0 else INK, j == 0, valign=MSO_ANCHOR.TOP)
link(s, .70, 6.35, 12.66, 6.35, RULE)
txt(s, "Primary extractor failure triggers a recorded fallback and human review—not silent success.",
    .80, 6.50, 11.83, .32, 12, MUTED)


# 6 — Detection and replacement
s = page("Layered PII detection, then precise replacement", "PII detection, classification and redaction")
label(s, "Existing detection layers", .72, 1.81, 5.28)
layers = (("01  Regex", "Emails, phones, employee IDs, SSNs, passport/PAN patterns, DOB and accounts."),
          ("02  Presidio", "spaCy en_core_web_lg helps identify names and supported PII entities."),
          ("03  Merge", "Filter business false positives; combine overlaps; propagate known names."))
for i, (name, body) in enumerate(layers):
    y = 2.43 + i * 1.07
    txt(s, name, .74, y, 1.46, .40, 14, BLUE, True)
    txt(s, body, 2.25, y - .02, 3.66, .83, 13, INK, valign=MSO_ANCHOR.TOP)
    if i < 2:
        link(s, .73, y + .88, 6.00, y + .88, RULE)
link(s, 6.32, 1.85, 6.32, 6.56, RULE)
label(s, "Synthetic before / after", 6.69, 1.81, 5.94)
txt(s, "BEFORE", 6.70, 2.45, 1.30, .28, 10, BLUE, True)
rect(s, 6.69, 2.78, 5.94, 1.05, WHITE, RULE)
txt(s, "Owner: Naomi K. Osadebe\nEmail: n.osadebe@example.com", 6.87, 2.92, 5.56, .76, 15, NAVY)
txt(s, "AFTER", 6.70, 4.17, 1.30, .28, 10, BLUE, True)
rect(s, 6.69, 4.48, 5.94, 1.05, PALE, BLUE)
txt(s, "Owner: [PERSON_1]\nEmail: [EMAIL_1]", 6.87, 4.62, 5.56, .76, 15, NAVY, True)
txt(s, "Character spans drive replacement; repeated values reuse a tag within one document.",
    6.70, 5.86, 5.89, .68, 12, MUTED, valign=MSO_ANCHOR.TOP)
txt(s, "GLiNER exists as an optional layer but was disabled for reported results.",
    .74, 6.44, 5.18, .30, 11, MUTED)


# 7 — Reliability, traceability, release
s = page("Measured reliability with a conservative gate", "Reliability, traceability and release control")
txt(s, "TARGET", .72, 1.76, 1.06, .28, 10, BLUE, True)
txt(s, "≥80% structure retained; PII coverage approaching 100%", 1.83, 1.67, 10.79, .48, 18, NAVY, True)
heads = ((.76, 1.53, "FILE"), (2.29, 2.12, "PII RECALL"), (4.41, 2.22, "STRUCTURE"),
         (6.63, 2.27, "COLAB STATUS"), (8.90, 3.67, "WHY"))
rect(s, .70, 2.39, 11.96, .47, PALE, None)
for x, w, val in heads:
    txt(s, val, x, 2.50, w, .21, 10, BLUE, True)
data = (("PPTX", "100%", "99.63%", "CLEARED", "No review warning"),
        ("DOCX", "97.96%", "97.67%", "REVIEW_REQUIRED", "PII in screenshots; vector image"),
        ("PDF", "99.16%", "Separate proxies*", "REVIEW_REQUIRED", "Low-confidence OCR; images / p.18 form"))
for i, row in enumerate(data):
    y = 2.86 + i * .67
    link(s, .70, y, 12.66, y, RULE)
    for j, ((x, w, _), val) in enumerate(zip(heads, row)):
        txt(s, val, x, y + .16, w - .08, .31, 13 if j < 4 else 12,
            NAVY if j in (0, 3) else INK, j in (0, 3))
link(s, .70, 4.88, 12.66, 4.88, RULE)
txt(s, "SECOND PASS", .74, 5.13, 1.45, .27, 10, BLUE, True)
txt(s, "Rescan output  +  exact-value leak check  +  independent PDF OCR comparison  →  one remediation pass",
    2.14, 5.03, 10.35, .53, 13, NAVY)
txt(s, "TRACE / CONTROL", .74, 5.80, 1.45, .27, 10, BLUE, True)
txt(s, "Masked audit: type, source locator, detector, offsets and reason. Only CLEARED writes ai_ready; review needs named sign-off.",
    2.14, 5.66, 10.35, .64, 13, NAVY, valign=MSO_ANCHOR.TOP)
txt(s, "* PDF: 95.12% headings, 15/15 sampled tables, 4/4 sampled figures. In-sample, single-annotator measures; zero detected residuals ≠ proof of zero PII.",
    .75, 6.47, 11.86, .41, 10, MUTED)


# 8 — Live walkthrough and conclusion
s = page("Live walkthrough and conclusion", "Demo sequence")
label(s, "Show in Colab", .72, 1.81, 7.37)
steps = ("1   Run all cells in the self-contained notebook.",
         "2   Upload the three synthetic PDF, DOCX and PPTX files.",
         "3   Show inventory, summary table and masked PII findings.",
         "4   Show redacted preview, verification and gate decisions.",
         "5   Download ZIP; inspect audit and CLEARED-only ai_ready folder.")
for i, value in enumerate(steps):
    y = 2.41 + i * .71
    txt(s, value, .78, y, 7.16, .49, 16, NAVY)
    if i < 4:
        link(s, .77, y + .59, 8.04, y + .59, RULE)
link(s, 8.39, 1.85, 8.39, 6.49, RULE)
label(s, "Takeaway", 8.72, 1.81, 3.90)
txt(s, "The release decision is the product.", 8.73, 2.47, 3.79, 1.10, 24, NAVY, True,
    valign=MSO_ANCHOR.TOP)
txt(s, "Detection reduces exposure; verification and human review control what can cross into AI.",
    8.73, 3.83, 3.80, 1.37, 16, INK, valign=MSO_ANCHOR.TOP)
txt(s, "If live execution stalls: use the saved summary and audit ZIP; do not claim review files were cleared.",
    .75, 6.42, 11.86, .35, 11, MUTED)

assert len(P.slides) == 8
P.save(OUTPUT)
print(OUTPUT, len(P.slides), "slides")

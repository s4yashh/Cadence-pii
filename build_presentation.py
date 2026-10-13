"""Generate a 10–15 minute stakeholder deck from measured, masked facts."""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent
prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
NAVY, BLUE, TEAL, PALE, WHITE, AMBER, RED = (
    RGBColor(18, 30, 54), RGBColor(41, 97, 169), RGBColor(0, 142, 142),
    RGBColor(235, 242, 247), RGBColor(255, 255, 255), RGBColor(238, 175, 51), RGBColor(185, 69, 65))


def rect(slide, x, y, w, h, fill, radius=False):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
                                   Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.fill.background()
    return shape


def text(slide, value, x, y, w, h, size=20, color=NAVY, bold=False, align=None):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = Inches(0.02)
    frame.margin_top = Inches(0.02)
    frame.text = value
    for p in frame.paragraphs:
        p.font.name = "Aptos"
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.color.rgb = color
        if align:
            p.alignment = align
    return box


def slide(title, subtitle=""):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    rect(s, 0, 0, 13.333, 0.16, TEAL)
    text(s, title, .65, .45, 12.0, .7, 30, NAVY, True)
    if subtitle:
        text(s, subtitle, .68, 1.22, 12.0, .5, 15, BLUE)
    text(s, f"CADENCE  |  OPTIV CASE STUDY 2                                      {len(prs.slides):02d}",
         .68, 7.16, 12, .22, 9, BLUE)
    return s


def card(s, heading, body, x, y, w=3.85, h=3.9, accent=TEAL):
    rect(s, x, y, w, h, PALE, True)
    rect(s, x, y, w, .11, accent)
    text(s, heading, x+.22, y+.3, w-.44, .7, 21, NAVY, True)
    text(s, body, x+.22, y+1.04, w-.44, h-1.2, 16, NAVY)


s = slide("PII detection before document AI", "A reviewable safety gate for three synthetic Cadence artifacts")
text(s, "Extract  •  Classify  •  Redact  •  Verify  •  Gate", .9, 2.2, 11.7, 1.0, 30, BLUE, True, PP_ALIGN.CENTER)
rect(s, 1.3, 3.5, 10.7, 1.5, PALE, True)
text(s, "Decision: only verified, cleared redacted text may cross into downstream AI.",
     1.65, 3.85, 10.0, .8, 23, NAVY, True, PP_ALIGN.CENTER)
text(s, "10–15 minute stakeholder walkthrough  |  13 October 2026", 1.2, 5.85, 11, .4, 15, BLUE, align=PP_ALIGN.CENTER)

s = slide("The policy constraint", "Employees use document analysis; PII must be removed before AI processing")
card(s, "Input", "PDF, DOCX and PPTX evidence\n\nScans, tables, diagrams, screenshots and native text", .65, 1.9)
card(s, "Risk", "Names, contact details and identifiers can hide in text or images.\n\nOCR can corrupt or omit them.", 4.73, 1.9, accent=AMBER)
card(s, "Outcome", "A masked audit trail plus a release decision.\n\nUncertain files go to human review.", 8.81, 1.9)

s = slide("File structure determines extraction", "Inspected supplied artifacts")
card(s, "35-page scanned PDF", "Image-only pages; no usable text layer.\n\nDocling layout + forced page OCR + figure crops + independent OCR view.", .65, 1.9)
card(s, "9-slide PPTX", "Org-chart cards and tables.\n\nNative shape walk preserves name/contact associations.", 4.73, 1.9)
card(s, "DOCX training guide", "Headings, tables and 35 screenshots.\n\nDocling for structure; embedded raster images OCR'd.", 8.81, 1.9)

s = slide("Functional blueprint", "Each stage records a source locator and can stop release")
labels = ["Validate", "Extract\n+ OCR", "Normalize\nblocks", "Detect\nPII", "Redact", "Verify", "Gate"]
for i, label in enumerate(labels):
    x = .42 + i * 1.84
    rect(s, x, 2.25, 1.63, 1.38, BLUE if i < 5 else TEAL, True)
    text(s, label, x+.08, 2.55, 1.47, .77, 17, WHITE, True, PP_ALIGN.CENTER)
    if i < len(labels)-1:
        text(s, "→", x+1.64, 2.66, .22, .5, 19, NAVY, True)
text(s, "Independent PDF OCR view + rescan + leak check → one remediation pass → final status",
     .76, 4.25, 11.8, .7, 19, NAVY, align=PP_ALIGN.CENTER)
text(s, "CLEARED → AI-ready text     REVIEW_REQUIRED → source review     BLOCKED/ERROR → no release",
     .76, 5.25, 11.8, .7, 17, BLUE, True, PP_ALIGN.CENTER)

s = slide("Technical boundary", "Local libraries in the active runtime; no document-content API call")
card(s, "Extraction", "Docling + python-docx / python-pptx\n\nTesseract for pages and embedded images\n\nBlock/page/slide locators", .65, 1.9)
card(s, "Detection", "Format-aware regex + Presidio/spaCy\n\nClean false positives, propagate names, resolve overlaps\n\nGLiNER off pending A/B", 4.73, 1.9)
card(s, "Release", "Offset-based typed placeholders\n\nRescan and cross-view check\n\nget_clean_text() only for CLEARED", 8.81, 1.9)

s = slide("Traceable redaction example", "Synthetic placeholder-only illustration")
rect(s, .7, 2.0, 11.9, 3.7, PALE, True)
text(s, "Source location: slide 4 / contact card / line 2", 1.0, 2.35, 11.2, .5, 18, BLUE, True)
text(s, "Detected: PERSON · EMAIL · PHONE", 1.0, 3.05, 11.2, .5, 19)
text(s, "Released text: Owner [PERSON_1]  •  [EMAIL_1]  •  [PHONE_1]", 1.0, 3.9, 11.2, .9, 23, NAVY, True)
text(s, "Audit: type, locator, offsets, detector, masked context, verification and status", 1.0, 5.02, 11.2, .45, 17, BLUE)

s = slide("Measured sample results", "In-sample gold set; one annotator; sampled PDF pages and DOCX regions")
cols = [(.73, "PPTX", "122 spans", "100% recall", "100% precision", "99.63% structure"),
        (4.74, "DOCX", "49 spans", "97.96% recall", "94.29% precision", "97.67% structure"),
        (8.75, "PDF", "238 spans", "99.16% recall", "99.22% precision", "95.12% headings*")]
for x, name, spans, recall, precision, structure in cols:
    card(s, name, f"{spans}\n\n{recall}\n{precision}\n\n{structure}", x, 1.85, 3.84, 4.15)
text(s, "* PDF uses separate proxies: 15/15 tables, 4/4 figures, 95.74% word recall vs independent OCR.",
     .79, 6.25, 11.9, .4, 13, BLUE)

s = slide("Release decisions and failure handling", "Verification found zero residual candidates; that is not a zero-risk guarantee")
card(s, "PPTX  ·  CLEARED", "Native text retained.\n\nNo extraction or verification warnings.\n\nAI-ready redacted text produced.", .65, 1.9)
card(s, "DOCX  ·  REVIEW", "Names in screenshots.\n\nOne body vector image is not OCR'd.\n\nVisual review required.", 4.73, 1.9, accent=AMBER)
card(s, "PDF  ·  REVIEW", "Low-confidence OCR regions, PII in figures and illegible p. 18 form.\n\nVisual review required.", 8.81, 1.9, accent=AMBER)

s = slide("Live walkthrough", "Run the self-contained Colab notebook top to bottom")
steps = ["1  Upload three synthetic artifacts", "2  Inspect inventory and extraction status",
         "3  Review category counts and masked findings", "4  Compare structure metadata with redacted preview",
         "5  Observe gate denial on review files", "6  Export redacted text and masked audit ZIP"]
for i, value in enumerate(steps):
    y = 1.76 + i*.78
    rect(s, .82, y, 11.7, .61, PALE, True)
    text(s, value, 1.12, y+.12, 11.0, .4, 18, NAVY)

s = slide("Limits and next steps", "Human review is part of the design")
card(s, "Known misses", "OCR-corrupted phone and name in the sampled PDF; one common-word name in DOCX.\n\nPage 18 form is illegible.", .65, 1.9, accent=AMBER)
card(s, "Evidence limits", "Gold is in-sample and single-annotator.\n\nHeld-out synthetic check: 50/50 spans, narrow formats only.\n\nGLiNER A/B not run.", 4.73, 1.9)
card(s, "Next actions", "Team spot-check gold and source images.\n\nRun notebook in Colab.\n\nBenchmark optional GLiNER and broader unseen documents.", 8.81, 1.9)

output = ROOT / "Optiv_Case_Study_2_Presentation.pptx"
prs.save(output)
print(output, len(prs.slides), "slides")

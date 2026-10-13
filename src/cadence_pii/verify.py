"""Independent verification of redacted output.

Three checks, each designed to catch a different failure mode:
1. Re-scan: regex + Presidio (lower threshold) on the redacted text, ignoring placeholders.
2. Leak check: every value that was redacted must not still appear verbatim elsewhere.
3. Cross-view (PDF): PII detected in the *independent* full-resolution Tesseract reading must not
   appear in the redacted text (catches values that Docling's OCR read differently or that
   detection missed in the primary view).
Passing these checks reduces risk; it does not prove zero residual PII.
"""
from __future__ import annotations

import re

from .config import DEFAULT, Settings
from .detect.run import detect_text, finalize
from .models import Finding
from .redact import PLACEHOLDER_RX

STRUCTURED = {"EMAIL", "PHONE", "EMPLOYEE_ID", "US_SSN", "PASSPORT", "TAX_ID", "FINANCIAL_ACCOUNT",
              "DATE_OF_BIRTH", "ADDRESS"}


def _outside_placeholders(text: str, f: Finding) -> bool:
    for m in PLACEHOLDER_RX.finditer(text, max(0, f.start - 40), f.end + 40):
        if m.start() <= f.start and f.end <= m.end():
            return False
    return not PLACEHOLDER_RX.fullmatch(f.value.strip())


def rescan(redacted: str, settings: Settings = DEFAULT) -> list:
    raw = detect_text(redacted, settings, presidio_threshold=settings.verify_presidio_threshold,
                      segments=_segments(redacted))
    fs = finalize(raw, redacted)
    out = []
    for f in fs:
        # finalize() unions overlapping spans; trim placeholders back out of the residual
        if not _outside_placeholders(redacted, f):
            continue
        if PLACEHOLDER_RX.search(f.value):
            continue
        out.append(f)
    return out


def _segments(text: str, size: int = 20000) -> list:
    """Split long text on paragraph boundaries for spaCy."""
    segs, s = [], 0
    while s < len(text):
        e = min(len(text), s + size)
        if e < len(text):
            k = text.rfind("\n\n", s, e)
            e = k if k > s else e
        segs.append((s, e))
        s = e
    return segs


def _leak_eligible(f) -> bool:
    """Only high-precision values are swept document-wide; a single NER token could be a common word."""
    v = f.value.strip()
    if len(v) < 4:
        return False
    if f.entity_type != "PERSON":
        return True
    return len(v.split()) >= 2 or "regex" in f.method


def leak_check(redacted: str, findings: list) -> list:
    out = []
    for v in sorted({f.value.strip() for f in findings if _leak_eligible(f)}):
        for m in re.finditer(re.escape(v), redacted):
            out.append(Finding("LEAK", m.start(), m.end(), v, 1.0, "leak_check", "verbatim_value"))
    return out


def cross_view(redacted: str, alt_text: str, settings: Settings = DEFAULT) -> list:
    if not alt_text:
        return []
    alt = finalize(detect_text(alt_text, settings, segments=_segments(alt_text)), alt_text)
    out, seen = [], set()
    for f in alt:
        v = f.value.strip()
        if len(v) < 4 or v in seen:
            continue
        seen.add(v)
        for m in re.finditer(re.escape(v), redacted):
            g = Finding(f.entity_type, m.start(), m.end(), v, f.score, "cross_view", f.recognizer)
            if _outside_placeholders(redacted, g):
                out.append(g)
    return out


def verify(redacted: str, findings: list, alt_text: str = "", settings: Settings = DEFAULT) -> dict:
    res = rescan(redacted, settings)
    leaks = leak_check(redacted, findings)
    xv = cross_view(redacted, alt_text, settings) if alt_text else []
    return {"rescan": res, "leaks": leaks, "cross_view": xv,
            "residual_count": len(res) + len(leaks) + len(xv)}

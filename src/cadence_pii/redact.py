"""Offset-based redaction with stable, typed placeholders.

The same value (normalised) always gets the same placeholder within one document, e.g. every
mention of one e-mail address becomes [EMAIL_2]. This is pseudonymisation for readability, not
anonymisation: the mapping exists only in memory and is never exported.
"""
from __future__ import annotations

import re

PLACEHOLDER_RX = re.compile(r"\[[A-Z_]+_\d+\]")


def _norm(etype: str, v: str) -> str:
    if etype in ("PHONE", "US_SSN", "FINANCIAL_ACCOUNT"):
        return re.sub(r"\D", "", v)
    return re.sub(r"[^a-z0-9]", "", v.lower())


def redact(text: str, findings: list, mapping: dict = None) -> tuple:
    """Return (redacted_text, mapping). Findings must be non-overlapping (merge.resolve guarantees it)."""
    mapping = {} if mapping is None else mapping
    counters: dict = {}
    for (etype, _k), ph in mapping.items():
        n = int(ph.rsplit("_", 1)[1].rstrip("]"))
        counters[etype] = max(counters.get(etype, 0), n)
    out, pos, cur = [], 0, 0
    for f in sorted(findings, key=lambda f: f.start):
        if f.start < pos:  # defensive: overlapping input
            continue
        key = (f.entity_type, _norm(f.entity_type, f.value))
        if key not in mapping:
            counters[f.entity_type] = counters.get(f.entity_type, 0) + 1
            mapping[key] = f"[{f.entity_type}_{counters[f.entity_type]}]"
        f.placeholder = mapping[key]
        out.append(text[pos:f.start])
        cur += f.start - pos
        f.red_start, f.red_end = cur, cur + len(f.placeholder)
        out.append(f.placeholder)
        cur += len(f.placeholder)
        pos = f.end
    out.append(text[pos:])
    return "".join(out), mapping


def masked_context(redacted: str, f, width: int = 60) -> str:
    """Shape-only snippet: verification can miss PII in neighbouring free text.

Preserve placeholder tags and spacing, but mask every other non-space character.
This keeps the audit safe even for REVIEW_REQUIRED text with OCR-corrupted PII.
"""
    if f.red_start < 0:
        return ""
    a, b = max(0, f.red_start - width), min(len(redacted), f.red_end + width)
    snippet = redacted[a:b]
    shaped = re.sub(r"\[[A-Z_]+_\d+\]|[^\s]", lambda m: m.group() if PLACEHOLDER_RX.fullmatch(m.group()) else "•", snippet)
    return ("…" if a else "") + shaped.replace("\n", " ⏎ ") + ("…" if b < len(redacted) else "")

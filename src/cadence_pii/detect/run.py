"""Run all enabled detection layers over a Document and return merged, located findings."""
from __future__ import annotations

from ..config import DEFAULT, Settings
from ..models import Document, Finding
from . import merge
from .regex_rules import detect_regex, non_pii_spans


class DetectorError(RuntimeError):
    """Raised when a detection layer fails; the pipeline must fail closed (status ERROR)."""


def detect_text(text: str, settings: Settings = DEFAULT, presidio_threshold=None, segments=None) -> list:
    """Raw findings from every enabled layer. `segments` = [(start, end)] to scan separately."""
    segments = segments or [(0, len(text))]
    thr = settings.presidio_threshold if presidio_threshold is None else presidio_threshold
    found = []
    for s, e in segments:
        seg = text[s:e]
        found += detect_regex(seg, s)
        if settings.use_presidio:
            try:
                from .presidio_det import detect_presidio
                found += detect_presidio(seg, s, thr)
            except Exception as ex:
                raise DetectorError(f"Presidio failed: {type(ex).__name__}: {ex}") from ex
        if settings.use_gliner:
            try:
                from .gliner_det import detect_gliner
                found += detect_gliner(seg, s, settings.gliner_model, settings.gliner_threshold)
            except Exception as ex:
                raise DetectorError(f"GLiNER failed: {type(ex).__name__}: {ex}") from ex
    return found


def finalize(raw: list, text: str, doc: Document = None) -> list:
    """Clean -> propagate known names -> resolve overlaps -> attach values and source locators."""
    fs = merge.clean(raw, text, non_pii_spans(text))
    fs += merge.propagate_names(fs, text)
    fs = merge.join_adjacent_persons(merge.resolve(merge.extend_initials(fs, text)), text)
    for f in fs:
        f.value = text[f.start:f.end]
        if doc is not None:
            b = doc.block_at(f.start)
            if b is not None:
                f.block_id, f.page = b.block_id, b.page
                # add the line within the block so table rows can be found quickly
                bstart = next(s for s, _e, bid in doc.spans if bid == b.block_id)
                line = text[bstart:f.start].count("\n") + 1
                f.locator = f"{b.locator} / line {line}"
    return fs


def detect_document(doc: Document, settings: Settings = DEFAULT) -> list:
    raw = detect_text(doc.text, settings, segments=[(s, e) for s, e, _ in doc.spans])
    return finalize(raw, doc.text, doc)

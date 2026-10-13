"""Data model shared by every pipeline stage."""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Status(str, Enum):
    PROCESSING = "PROCESSING"
    CLEARED = "CLEARED"                  # verified; text may go to the downstream AI
    REVIEW_REQUIRED = "REVIEW_REQUIRED"  # a human must look before release
    BLOCKED = "BLOCKED"                  # residual PII found after redaction; never release
    ERROR = "ERROR"                      # could not be processed (corrupt / unsupported / crash)


@dataclass
class Block:
    """One structural unit of extracted text, in reading order."""
    block_id: int
    locator: str                 # human-readable source location, e.g. "page 21 / table 3"
    kind: str                    # heading | paragraph | list_item | table | caption | image_ocr | page_ocr | notes | furniture
    text: str
    source: str                  # docling | native | tesseract
    page: Optional[int] = None   # page / slide number where known
    ocr_conf: Optional[float] = None  # mean word confidence (0-100) for OCR-derived text
    ocr_words: int = 0


@dataclass
class Finding:
    entity_type: str
    start: int                   # offsets into Document.text (the exact string that was scanned)
    end: int
    value: str                   # raw value: kept in memory only, never written to reports
    score: float
    method: str                  # regex | presidio | gliner | cross_view
    recognizer: str
    block_id: int = -1
    locator: str = ""
    placeholder: str = ""
    red_start: int = -1          # placeholder position in the redacted text
    red_end: int = -1
    page: Optional[int] = None

    def public(self, context: str = "") -> dict:
        d = asdict(self)
        d.pop("value")
        d["value_masked"] = mask_value(self.value)
        d["context_masked"] = context
        return d


@dataclass
class Document:
    """Normalised extraction output: one string plus a block index for traceability."""
    filename: str
    filetype: str
    blocks: list = field(default_factory=list)
    text: str = ""
    spans: list = field(default_factory=list)   # (start, end, block_id) per block, sorted
    warnings: list = field(default_factory=list)  # [{"level": "review"|"info", "msg": str}] -> feed the gate
    alt_views: dict = field(default_factory=dict)  # e.g. {"tesseract": "..."} for cross-checks
    inventory: dict = field(default_factory=dict)

    def warn(self, msg: str, level: str = "review") -> None:
        """Record an extraction issue. 'review' issues stop a file being CLEARED; 'info' is audit-only."""
        self.warnings.append({"level": level, "msg": msg})

    @staticmethod
    def render_block(b: Block) -> str:
        if b.kind == "heading":
            return "## " + b.text
        if b.kind == "list_item":
            return "- " + b.text
        if b.kind == "image_ocr":
            return f"[image text: {b.locator}]\n{b.text}"
        return b.text

    def assemble(self) -> None:
        """Build self.text from blocks, recording each block's character span."""
        parts, spans, pos = [], [], 0
        for b in self.blocks:
            s = self.render_block(b)
            if not s.strip():
                continue
            spans.append((pos, pos + len(s), b.block_id))
            parts.append(s)
            pos += len(s) + 2
        self.text = "\n\n".join(parts)
        self.spans = spans

    def block_at(self, offset: int) -> Optional[Block]:
        starts = [s[0] for s in self.spans]
        i = bisect.bisect_right(starts, offset) - 1
        if i < 0:
            return None
        bid = self.spans[i][2]
        return next((b for b in self.blocks if b.block_id == bid), None)


@dataclass
class FileResult:
    filename: str
    filetype: str = ""
    sha256: str = ""
    size_bytes: int = 0
    status: Status = Status.PROCESSING
    reasons: list = field(default_factory=list)
    document: Optional[Document] = None
    findings: list = field(default_factory=list)
    redacted_text: str = ""
    verification: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    review_log: list = field(default_factory=list)  # human sign-offs (who, when, note)


def mask_value(v: str) -> str:
    """Show only shape: first character + length, digits/letters masked. Never reveals the value."""
    v = v.strip()
    if not v:
        return ""
    keep = v[0] if v[0].isalpha() else "*"
    return f"{keep}{'*' * (min(len(v), 12) - 1)} ({len(v)} chars)"

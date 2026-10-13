"""Release gate. Only CLEARED text can be handed to the downstream AI agent."""
from __future__ import annotations

from datetime import datetime, timezone

from .config import DEFAULT, Settings
from .models import FileResult, Status


class ReleaseBlocked(PermissionError):
    pass


def decide(r: FileResult, settings: Settings = DEFAULT) -> FileResult:
    """Set r.status and r.reasons from extraction warnings, OCR quality and verification results."""
    if r.status == Status.ERROR:
        return r
    reasons = []
    doc = r.document
    for w in doc.warnings:
        if w["level"] == "review":
            reasons.append(("REVIEW", w["msg"]))
    for b in doc.blocks:
        if b.kind == "image_ocr" and b.ocr_conf is not None and b.ocr_words >= settings.ocr_min_words_for_conf \
                and b.ocr_conf < settings.ocr_min_block_conf:
            reasons.append(("REVIEW", f"low OCR confidence ({b.ocr_conf}) for {b.locator}"))
    pii_images = sorted({f.locator.split(" / line")[0] for f in r.findings
                         if (b := doc.block_at(f.start) if f.start >= 0 else None) is not None and b.kind == "image_ocr"})
    if pii_images:
        reasons.append(("REVIEW", f"{len(pii_images)} embedded image(s) contain PII; OCR may miss garbled or partial "
                                  f"names - visually confirm: {', '.join(pii_images[:5])}{' ...' if len(pii_images) > 5 else ''}"))
    v = r.verification.get("final", {})
    if v.get("residual_count", 0) > 0:
        reasons.append(("BLOCK", f"{v['residual_count']} residual PII candidate(s) remain after remediation"))
    if not r.findings and len(doc.text) > 2000:
        reasons.append(("REVIEW", "no PII found in a substantial document - confirm this is expected"))

    if any(k == "BLOCK" for k, _ in reasons):
        r.status = Status.BLOCKED
    elif reasons:
        r.status = Status.REVIEW_REQUIRED
    else:
        r.status = Status.CLEARED
    r.reasons = [f"{k}: {m}" for k, m in reasons]
    return r


def approve(r: FileResult, reviewer: str, note: str) -> FileResult:
    """Human sign-off for REVIEW_REQUIRED files. BLOCKED/ERROR files cannot be approved."""
    if r.status != Status.REVIEW_REQUIRED:
        raise ReleaseBlocked(f"only REVIEW_REQUIRED files can be approved (status is {r.status.value})")
    if not reviewer.strip() or not note.strip():
        raise ValueError("reviewer name and review note are required")
    r.review_log.append({"reviewer": reviewer, "note": note, "at": datetime.now(timezone.utc).isoformat(),
                         "reasons_reviewed": list(r.reasons)})
    r.status = Status.CLEARED
    return r


def get_clean_text(r: FileResult) -> str:
    """The only path to downstream-AI text. Raises unless the file is CLEARED."""
    if r.status != Status.CLEARED:
        raise ReleaseBlocked(f"{r.filename}: status {r.status.value} - not released to downstream AI")
    return r.redacted_text

"""Audit reporting and exports. Reports contain types, counts, locators and masked context only."""
from __future__ import annotations

import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import ENTITY_TYPES
from .models import Status
from .redact import masked_context


def summary_table(results) -> pd.DataFrame:
    rows = []
    for r in results:
        c = Counter(f.entity_type for f in r.findings)
        d = r.document
        row = {"file": r.filename, "type": r.filetype, "status": r.status.value,
               "pages/slides": (d.inventory.get("pages_or_slides") if d else None),
               "blocks": len(d.blocks) if d else 0, "PII findings": len(r.findings)}
        row.update({t: c.get(t, 0) for t in ENTITY_TYPES})
        row.update({"review reasons": len(r.reasons), "residual after verify":
                    r.verification.get("final", {}).get("residual_count"), "secs": round(sum(r.timings.values()), 1)})
        rows.append(row)
    return pd.DataFrame(rows)


def findings_table(r, limit=None) -> pd.DataFrame:
    rows = []
    for f in sorted(r.findings, key=lambda f: (f.red_start if f.red_start >= 0 else 10**12)):
        p = f.public(masked_context(r.redacted_text, f))
        rows.append({k: p[k] for k in ("entity_type", "placeholder", "locator", "method", "recognizer", "score",
                                       "value_masked", "context_masked")})
    df = pd.DataFrame(rows)
    return df.head(limit) if limit else df


def audit_record(r) -> dict:
    d = r.document
    return {
        "file": r.filename, "file_type": r.filetype, "sha256": r.sha256, "size_bytes": r.size_bytes,
        "status": r.status.value, "reasons": r.reasons, "errors": [e for e in r.errors if "Traceback" not in e],
        "inventory": d.inventory if d else {}, "extraction_warnings": d.warnings if d else [],
        "counts_by_type": dict(Counter(f.entity_type for f in r.findings)),
        "counts_by_method": dict(Counter(f.method for f in r.findings)),
        "verification": r.verification, "timings_s": r.timings, "review_log": r.review_log,
        "findings": [f.public(masked_context(r.redacted_text, f)) for f in r.findings],
    }


def export(results, outdir="outputs") -> Path:
    """Write redacted text for every processed file, AI-ready copies only for CLEARED files, plus audit files."""
    out = Path(outdir)
    (out / "redacted").mkdir(parents=True, exist_ok=True)
    (out / "ai_ready").mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for r in results:
        stem = Path(r.filename).stem
        if r.redacted_text:
            header = f"<!-- {r.filename} | status {r.status.value} | redacted {stamp} -->\n\n"
            (out / "redacted" / f"{stem}.redacted.md").write_text(header + r.redacted_text, encoding="utf-8")
        ai = out / "ai_ready" / f"{stem}.md"
        if r.status == Status.CLEARED:
            ai.write_text(r.redacted_text, encoding="utf-8")
        elif ai.exists():
            ai.unlink()  # never leave a stale release behind
    audit = {"generated_at": stamp, "files": [audit_record(r) for r in results]}
    (out / "audit_report.json").write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
    rows = []
    for r in results:
        for f in r.findings:
            p = f.public(masked_context(r.redacted_text, f))
            rows.append({"file": r.filename, **{k: p[k] for k in ("entity_type", "placeholder", "locator", "page",
                                                                  "start", "end", "method", "recognizer", "score",
                                                                  "value_masked", "context_masked")}})
    pd.DataFrame(rows).to_csv(out / "findings.csv", index=False)
    (out / "summary.html").write_text(_html(results, stamp), encoding="utf-8")
    return out


def _html(results, stamp) -> str:
    colors = {"CLEARED": "#1a7f37", "REVIEW_REQUIRED": "#9a6700", "BLOCKED": "#cf222e", "ERROR": "#6e7781"}
    parts = [f"<h1>Cadence PII scan - audit summary</h1><p>Generated {stamp}. No raw PII values are included.</p>",
             summary_table(results).to_html(index=False)]
    for r in results:
        parts.append(f"<h2>{html.escape(r.filename)} - <span style='color:{colors.get(r.status.value)}'>"
                     f"{r.status.value}</span></h2>")
        if r.reasons:
            parts.append("<ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in r.reasons) + "</ul>")
        if r.findings:
            parts.append(findings_table(r).to_html(index=False))
    return "<html><head><meta charset='utf-8'><style>body{font-family:sans-serif;margin:2em}table{border-collapse:collapse;font-size:12px}td,th{border:1px solid #ccc;padding:3px 6px}</style></head><body>" + "".join(parts) + "</body></html>"

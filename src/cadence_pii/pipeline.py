"""End-to-end orchestration. One bad file never stops the batch; failures become ERROR results."""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

from . import gate
from .config import DEFAULT, Settings
from .detect.run import detect_document
from .extract import extract
from .ingest import ValidationError, validate
from .models import FileResult, Finding, Status
from .redact import redact
from .verify import verify


def _locate(doc, value: str):
    i = doc.text.find(value)
    return doc.block_at(i) if i >= 0 else None


def run_file(path, settings: Settings = DEFAULT) -> FileResult:
    path = Path(path)
    r = FileResult(filename=path.name)
    t = {}
    try:
        t0 = time.time()
        r.__dict__.update(validate(path, settings))
        t["validate"] = round(time.time() - t0, 2)

        t0 = time.time()
        doc = extract(path, settings)
        r.document = doc
        t["extract"] = round(time.time() - t0, 1)
        if not doc.text.strip():
            r.status = Status.ERROR
            r.errors.append("no text could be extracted")
            return r

        t0 = time.time()
        r.findings = detect_document(doc, settings)
        t["detect"] = round(time.time() - t0, 1)

        t0 = time.time()
        redacted, mapping = redact(doc.text, r.findings)
        t["redact"] = round(time.time() - t0, 2)

        t0 = time.time()
        alt = doc.alt_views.get("tesseract", "")
        v1 = verify(redacted, r.findings, alt, settings)
        r.verification["initial"] = _summ(v1)
        # one remediation pass: redact what verification found, then verify again
        extra = v1["rescan"] + v1["cross_view"] + [Finding("LEAK", f.start, f.end, f.value, 1, f.method, f.recognizer)
                                                    for f in v1["leaks"]]
        if extra:
            from .detect.merge import resolve
            fix = resolve(extra)
            for f in fix:
                f.value = redacted[f.start:f.end]
                if f.entity_type == "LEAK":
                    orig = next((g for g in r.findings if g.value.strip() == f.value.strip()), None)
                    f.entity_type = orig.entity_type if orig else "PERSON"
            redacted, mapping = redact(redacted, fix, mapping)
            deltas = [(f.start, len(f.placeholder) - (f.end - f.start)) for f in fix]
            for f in fix:
                i = doc.text.find(f.value)  # report offsets in the extracted-text coordinate system
                f.start, f.end = (i, i + len(f.value)) if i >= 0 else (-1, -1)
                b = _locate(doc, f.value)
                f.block_id, f.page = (b.block_id, b.page) if b else (-1, None)
                f.locator = (b.locator if b else "unknown") + " (remediation pass)"
                f.method = "verify:" + f.method
            # recompute placeholder positions of the original findings in the final text
            r.findings = _shift(r.findings, deltas) + fix
            v2 = verify(redacted, r.findings, alt, settings)
        else:
            v2 = v1
        r.verification["final"] = _summ(v2)
        r.verification["remediated"] = len(extra)
        r.redacted_text = redacted
        t["verify"] = round(time.time() - t0, 1)
        gate.decide(r, settings)
    except ValidationError as e:
        r.status = Status.ERROR
        r.errors.append(f"validation: {e}")
    except Exception as e:  # fail closed on anything unexpected (detector crash, OCR failure...)
        r.status = Status.ERROR
        r.errors.append(f"{type(e).__name__}: {e}")
        r.errors.append(traceback.format_exc(limit=3))
        r.redacted_text = ""
    finally:
        r.timings = t
    return r


def _shift(findings, deltas):
    """After the remediation pass, move first-pass placeholder offsets by the length change of every
    remediation edit that lies before them."""
    for f in findings:
        d = sum(dl for s, dl in deltas if s < f.red_start)
        f.red_start += d
        f.red_end += d
    return findings


def _summ(v: dict) -> dict:
    """Verification summary with no raw values (types and counts only)."""
    def types(lst):
        out = {}
        for f in lst:
            out[f.entity_type] = out.get(f.entity_type, 0) + 1
        return out
    return {"residual_count": v["residual_count"], "rescan": types(v["rescan"]), "leaks": len(v["leaks"]),
            "cross_view": types(v["cross_view"])}


def run_batch(paths, settings: Settings = DEFAULT, progress=print) -> list:
    results = []
    for p in paths:
        progress(f"processing {Path(p).name} ...")
        r = run_file(p, settings)
        progress(f"  -> {r.status.value} ({sum(r.timings.values()):.0f}s, {len(r.findings)} findings)")
        results.append(r)
    return results


if __name__ == "__main__":
    from .report import export, summary_table
    res = run_batch(sys.argv[1:])
    print(summary_table(res).to_string())
    print("exported to", export(res, "outputs", source_paths=sys.argv[1:]))

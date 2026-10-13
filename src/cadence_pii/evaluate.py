"""Evaluation against the manually annotated gold set + structure-retention measurement.

Metrics (computed per region, aggregated per file):
* redaction recall  - share of gold PII spans fully covered by some redaction (privacy metric)
* typed recall      - share fully covered by a redaction of the same category
* precision         - share of predicted spans that overlap a gold (or optional) span
* context retention - share of non-PII characters in the region that survive redaction
Structure retention (see structure_docx_pptx / structure_pdf) is reported separately.
"""
from __future__ import annotations

import difflib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .config import CATEGORY
from .models import mask_value


def region_segments(doc, sel: dict) -> list:
    out = []
    for (s, e, bid) in doc.spans:
        b = next(x for x in doc.blocks if x.block_id == bid)
        if "page" in sel and b.page != sel["page"]:
            continue
        if "locator_contains" in sel and sel["locator_contains"] not in b.locator:
            continue
        if b.kind in sel.get("exclude_kinds", []):
            continue
        out.append((s, e))
    return out


def _find_all(text, segs, value):
    spans = []
    for s, e in segs:
        i = text.find(value, s, e)
        while i >= 0 and i + len(value) <= e:
            spans.append((i, i + len(value)))
            i = text.find(value, i + 1, e)
    return spans


def _drop_contained(spans):
    """Gold spans contained in a longer gold span ("Rafael" inside "Rafael E. Duarte") are one mention."""
    out = []
    for sp in spans:
        if not any(o != sp and o[0] <= sp[0] and sp[1] <= o[1] and (o[1] - o[0]) > (sp[1] - sp[0])
                   for o in spans):
            out.append(sp)
    return sorted(set(out), key=lambda x: (x[0], x[1]))


def _covered(text, span, preds, same_cat=None):
    """True if every non-space character of the gold span lies inside a predicted span."""
    s, e = span
    pos = [i for i in range(s, e) if not text[i].isspace() and text[i] not in "|"]
    for i in pos:
        if not any(p.start <= i < p.end and (same_cat is None or CATEGORY.get(p.entity_type) == same_cat)
                   for p in preds):
            return False
    return True


def evaluate_file(result, gold: dict) -> dict:
    doc = result.document
    text = doc.text
    agg = Counter()
    per_type = defaultdict(Counter)
    missed, fps, gold_errors = [], [], []
    region_rows = []
    for reg in gold["regions"]:
        segs = region_segments(doc, reg["selector"])
        if not segs:
            gold_errors.append(f"{reg['id']}: selector matched no blocks")
            continue
        gspans, gtype = [], {}
        for etype, val in reg["items"]:
            found = _find_all(text, segs, val)
            if not found:
                gold_errors.append(f"{reg['id']}: gold value not found in text ({etype}, {mask_value(val)})")
            for sp in found:
                gspans.append(sp)
                gtype.setdefault(sp, etype)
        gspans = _drop_contained(gspans)
        ospans = [sp for etype, val in reg.get("optional", []) for sp in _find_all(text, segs, val)]
        preds = [f for f in result.findings if f.start >= 0 and any(f.start < e and s < f.end for s, e in segs)]
        r = Counter()
        for sp in gspans:
            t = gtype[sp]
            ok = _covered(text, sp, preds)
            ok_typed = ok and _covered(text, sp, preds, CATEGORY.get(t))
            r["gold"] += 1
            r["redacted"] += ok
            r["typed"] += ok_typed
            per_type[t]["gold"] += 1
            per_type[t]["redacted"] += ok
            per_type[t]["typed"] += ok_typed
            if not ok:
                touched = any(p.start < sp[1] and sp[0] < p.end for p in preds)
                r["partial"] += touched
                missed.append({"region": reg["id"], "type": t, "kind": "partial" if touched else "missed",
                               "value_masked": mask_value(text[sp[0]:sp[1]]), "_raw": text[sp[0]:sp[1]]})
        for p in preds:
            hit = any(p.start < e and s < p.end for s, e in gspans + ospans)
            r["pred"] += 1
            r["tp_pred"] += hit
            per_type[p.entity_type]["pred"] += 1
            per_type[p.entity_type]["tp_pred"] += hit
            if not hit:
                fps.append({"region": reg["id"], "type": p.entity_type, "method": p.method,
                            "value_masked": mask_value(p.value), "_raw": p.value})
        # context retention: characters outside gold/optional PII that were nevertheless redacted
        region_chars = sum(e - s for s, e in segs)
        pii_chars = set()
        for s, e in gspans + ospans:
            pii_chars.update(range(s, e))
        over = set()
        for p in preds:
            over.update(i for i in range(max(p.start, 0), p.end) if i not in pii_chars
                        and any(s <= i < e for s, e in segs) and not text[i].isspace())
        nonpii = sum(1 for s, e in segs for i in range(s, e) if i not in pii_chars and not text[i].isspace())
        r["nonpii_chars"] += nonpii
        r["over_chars"] += len(over)
        agg.update(r)
        region_rows.append({"region": reg["id"], **r, "chars": region_chars})
    def ratio(a, b):
        return round(a / b, 4) if b else None
    recall = ratio(agg["redacted"], agg["gold"])
    precision = ratio(agg["tp_pred"], agg["pred"])
    summary = {
        "file": gold["file"], "regions": len(region_rows), "gold_spans": agg["gold"], "predicted_spans": agg["pred"],
        "redaction_recall": recall, "typed_recall": ratio(agg["typed"], agg["gold"]),
        "precision": precision, "f1": round(2 * precision * recall / (precision + recall), 4)
        if precision is not None and recall is not None and precision + recall else None,
        "context_retention": ratio(agg["nonpii_chars"] - agg["over_chars"], agg["nonpii_chars"]),
        "not_fully_redacted": len(missed), "of_which_partial": agg["partial"],
        "entirely_missed": len(missed) - agg["partial"], "false_positives": len(fps),
        "per_type": {t: {"gold": c["gold"], "redaction_recall": ratio(c["redacted"], c["gold"]),
                         "typed_recall": ratio(c["typed"], c["gold"]), "predicted": c["pred"],
                         "precision": ratio(c["tp_pred"], c["pred"])} for t, c in sorted(per_type.items())},
    }
    return {"summary": summary, "regions": region_rows, "missed": missed, "false_positives": fps,
            "gold_errors": gold_errors}


# ----------------------------------------------------------------------------- structure retention
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def _lis_len(seq):
    import bisect
    tails = []
    for x in seq:
        i = bisect.bisect_left(tails, x)
        tails[i:i + 1] = [x]
    return len(tails)


def structure_docx_pptx(path, extracted_doc) -> dict:
    """Reference = python-docx / python-pptx parse of the OOXML (no OCR). For every reference element
    (heading, paragraph, list item, table cell) check: text retained, element type retained, and order
    retained (longest increasing subsequence of matched positions). Score = elements satisfying all three."""
    from .extract.native_ext import extract_native
    ref = extract_native(path, ocr=False)
    ext_text = _norm(extracted_doc.text)
    kinds_by_text = defaultdict(set)
    table_text = _norm(" ".join(b.text for b in extracted_doc.blocks if b.kind == "table"))
    for b in extracted_doc.blocks:
        kinds_by_text[_norm(b.text)].add(b.kind)
    elements = []
    for b in ref.blocks:
        if b.kind == "table":
            rows = b.text.split("\n")
            for row in rows[:1] + rows[2:]:  # skip the markdown separator line
                for cell in row.strip("|").split("|"):
                    if _norm(cell):
                        elements.append(("table_cell", _norm(cell)))
        elif b.kind in ("heading", "paragraph", "list_item", "notes"):
            elements.append((b.kind, _norm(b.text)))
    found, typed, positions, cursor = 0, 0, [], 0
    per_kind = defaultdict(Counter)
    for kind, t in elements:
        if not t:
            continue
        per_kind[kind]["total"] += 1
        i = ext_text.find(t, cursor)
        if i < 0:
            i = ext_text.find(t)
        if i < 0:
            continue
        found += 1
        per_kind[kind]["text"] += 1
        if len(t) >= 4:  # 1-3 char cells ("A", "R" in RACI tables) are ambiguous for ordering
            positions.append(i)
            cursor = i
        if kind == "table_cell":
            ok = t in table_text
        elif kind == "heading":
            ok = "heading" in kinds_by_text.get(t, set()) or any(t == k for k, v in kinds_by_text.items() if "heading" in v)
        elif kind == "list_item":
            ok = "list_item" in kinds_by_text.get(t, set()) or "paragraph" in kinds_by_text.get(t, set())
        else:
            ok = True
        typed += ok
        per_kind[kind]["typed"] += ok
    total = sum(c["total"] for c in per_kind.values())
    in_order = _lis_len(positions)
    order_ratio = in_order / len(positions) if positions else 1.0
    return {"reference": "native OOXML parse", "elements": total,
            "text_retained": round(found / total, 4) if total else None,
            "type_retained": round(typed / total, 4) if total else None,
            "order_retained": round(order_ratio, 4),
            # element counts only if its text and its type survived, discounted by the share out of order
            "structure_retention": round(typed / total * order_ratio, 4) if total else None,
            "per_kind": {k: dict(v) for k, v in per_kind.items()}}


def structure_pdf(extracted_doc, gold: dict) -> dict:
    """No native reference exists (image-only PDF). Two proxies:
    1. headings: numbered section headings found in the independent Tesseract reading, matched (fuzzy >= 0.85)
       to Docling heading blocks;
    2. tables / figures on the manually counted sample pages vs Docling's detected tables / figures;
    plus word-level content recall of Docling text against the Tesseract reading."""
    tv = extracted_doc.alt_views.get("tesseract", "")
    ref_heads = [_norm(m.group(0)) for m in re.finditer(r"(?m)^\d{1,2}(?:\.\d{1,2})?\.?\s+[A-Z][^\n]{3,80}$", tv)]
    ref_heads = [h for h in ref_heads if len(h.split()) <= 12]
    got_heads = [_norm(b.text) for b in extracted_doc.blocks if b.kind == "heading"]
    matched = sum(1 for h in ref_heads if difflib.get_close_matches(h, got_heads, 1, 0.85))
    ref = gold.get("structure_reference", {}).get("pages", {})
    t_ref = t_got = f_ref = f_got = 0
    for p, c in ref.items():
        p = int(p)
        t_ref += c["tables"]
        f_ref += c["figures"]
        t_got += min(c["tables"], sum(1 for b in extracted_doc.blocks if b.page == p and b.kind == "table"))
        f_got += min(c["figures"], sum(1 for b in extracted_doc.blocks if b.page == p and b.kind == "image_ocr"))
    words = lambda s: Counter(w for w in re.findall(r"[a-z]{3,}", s.lower()))
    wr, wd = words(tv), words(extracted_doc.text)
    content = sum(min(n, wd[w]) for w, n in wr.items()) / max(1, sum(wr.values()))
    return {"reference": "independent Tesseract reading + manual table/figure count on sample pages",
            "headings_ref": len(ref_heads), "headings_matched": matched,
            "heading_retention": round(matched / len(ref_heads), 4) if ref_heads else None,
            "tables_ref": t_ref, "tables_detected": t_got, "table_retention": round(t_got / t_ref, 4) if t_ref else None,
            "figures_ref": f_ref, "figures_ocrd": f_got, "figure_retention": round(f_got / f_ref, 4) if f_ref else None,
            "word_content_recall_vs_tesseract": round(content, 4)}


def save_sanitized(results: dict, path) -> None:
    """Write evaluation output without raw values (strip the private `_raw` keys)."""
    def strip(o):
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if not k.startswith("_")}
        if isinstance(o, list):
            return [strip(x) for x in o]
        return o
    Path(path).write_text(json.dumps(strip(results), indent=2), encoding="utf-8")

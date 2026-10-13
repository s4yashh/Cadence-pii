"""Reproduce the case-study measurements without publishing raw evidence text.

Default mode runs the complete pipeline. --cached reuses local development results
and is only valid when the extraction and detection code has not changed.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cadence_pii.evaluate import evaluate_file, save_sanitized, structure_docx_pptx, structure_pdf
from cadence_pii.pipeline import run_file

FILES = {
    "pptx": "Cadence_Financial_Group_Organizational_Pack.pptx",
    "docx": "Cadence_TPRM_Training.docx",
    "pdf": "Cadence_Group_Risk_Management_Policy__v6.0.pdf",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("formats", nargs="*", choices=list(FILES))
    parser.add_argument("--cached", action="store_true", help="reuse trusted local scratch results")
    args = parser.parse_args()
    out = ROOT / "evaluation" / "results"
    out.mkdir(parents=True, exist_ok=True)
    for kind in args.formats or FILES:
        filename = FILES[kind]
        path = ROOT / "Case Study 2 Supporting Material" / filename
        if args.cached:
            with (ROOT / "scratch" / f"res_{filename}.pkl").open("rb") as handle:
                result = pickle.load(handle)
        else:
            result = run_file(path)
        if result.document is None:
            raise RuntimeError(f"{kind}: pipeline produced no document ({result.status.value})")
        gold = json.loads((ROOT / "evaluation" / "gold" / f"{kind}_gold.json").read_text())
        measured = evaluate_file(result, gold)
        measured["structure"] = (structure_pdf(result.document, gold) if kind == "pdf"
                                 else structure_docx_pptx(path, result.document))
        measured["run"] = {"mode": "cached development result" if args.cached else "full pipeline",
                           "status": result.status.value, "timings_s": result.timings,
                           "gold": "single-annotator, in-sample; team spot-check pending"}
        if measured["gold_errors"]:
            raise RuntimeError(f"{kind}: {len(measured['gold_errors'])} gold selector/value errors")
        save_sanitized(measured, out / f"{kind}.json")
        print(f"{kind}: recall={measured['summary']['redaction_recall']:.4f}, "
              f"precision={measured['summary']['precision']:.4f}, "
              f"status={result.status.value}, structure={measured['structure'].get('structure_retention', 'proxies only')}")


if __name__ == "__main__":
    main()

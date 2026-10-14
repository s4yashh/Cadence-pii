# Cadence PII Detection — Optiv Case Study 2

This project extracts text from the three supplied synthetic PDF, DOCX and PPTX artifacts, detects and classifies PII, replaces it with typed placeholders, verifies the redaction, and gates downstream release. The walkthrough is [Cadence_PII_Detection.ipynb](Cadence_PII_Detection.ipynb); the stakeholder deck is [Optiv_Case_Study_2_Presentation.pptx](Optiv_Case_Study_2_Presentation.pptx).

## Run the walkthrough

In Google Colab, upload the notebook, choose **Runtime → Run all**, and upload the three supplied artifacts when prompted. It installs pinned Python packages, Tesseract, the Linux OpenGL library needed by some Docling/OpenCV installs, and `en_core_web_lg` into the runtime. Installation may take several minutes; PDF extraction is CPU intensive. A preflight cell checks that Docling imports before upload, so an import failure is visible immediately. The notebook is self-contained: `build_notebook.py` embeds every module from `src/cadence_pii/` as a `%%writefile` cell. Rebuild it after changing source code.

If hosted processing is prohibited by your policy, run the notebook locally in Jupyter and set `CADENCE_INPUT_DIR` to the input folder. Colab processes files in a hosted runtime; it is not local to your computer. These supplied artifacts are explicitly marked synthetic. No document content is sent to an external extraction or AI API, although package/model setup downloads dependencies.

Local setup on macOS/Linux with Python 3.12:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m spacy download en_core_web_lg
# Install the tesseract-ocr system package using your OS package manager.
.venv/bin/python build_notebook.py
PYTHONPATH=src .venv/bin/python -m cadence_pii.pipeline "Case Study 2 Supporting Material/"*
```

The CLI exports to `outputs/`: `redacted/` for processed text, `review_copies/` for same-extension **text-only reconstructions**, `layout_review/` for visual review drafts, `ai_ready/` for `CLEARED` text only, and masked `audit_report.json`, `findings.csv`, and `summary.html`. In `layout_review/`, the PowerPoint copy preserves original shapes and slide geometry while replacing detected PII in editable text; original pictures remain. The scanned-PDF draft preserves page dimensions and visible layout by rendering pages to images and painting over PII located by a fresh OCR pass. Its `visual_redaction_stats.json` reports original findings that could **not** be located for painting. The Word draft preserves original paragraphs, tables and images while replacing detected PII in editable text; its statistics report known image findings that remain unredacted. None of these visual drafts is a complete privacy-cleared document. They are for private side-by-side review, not downstream AI or external sharing. `REVIEW_REQUIRED` needs source review and an accountable `gate.approve` sign-off; `BLOCKED` and `ERROR` cannot be released. Original evidence is never modified. Exports are still sensitive to undetected OCR errors and should be handled privately.

## Verify and evaluate

```bash
.venv/bin/python -m pytest tests -q
.venv/bin/python evaluation/run_evaluation.py
.venv/bin/python evaluation/heldout.py
```

The first evaluation command runs the full pipeline when the supplied source artifacts and local `evaluation/gold/` annotations are available; these are intentionally not stored in Git. For quick development after a detection-only change, `--cached` uses local scratch pickles, which may be stale if extraction code changed. The gold JSON and `scratch/` caches contain raw **synthetic** values; do not publish them as a public report. The in-sample set needs an independent spot-check.

The notebook has been executed locally cell by cell using `verify_notebook.py`, and a later Colab run completed using Docling for the PDF and DOCX. Its audit reported no pipeline errors and zero detected residuals. The PPTX was `CLEARED`; the PDF and DOCX remained `REVIEW_REQUIRED` because source images and low-confidence OCR regions need human inspection. A prior Colab run had a Pillow import mismatch; if the notebook's preflight detects it, choose **Runtime → Restart session**, then **Run all**. To repeat local verification, run `.venv/bin/python verify_notebook.py` from this folder with the input artifacts available. It runs the same cells, skipping Colab-only branches.

## Project map

`src/cadence_pii/` is the modular pipeline. `tests/` contains synthetic fixtures. `evaluation/` contains reproducible evaluation scripts; local gold annotations and generated results are excluded from Git. `build_presentation.py` regenerates the PowerPoint deck. `scratch/` contains development-only caches and raw synthetic extracted text, and is not required for the notebook.

The pipeline can miss PII corrupted by OCR or inside unreadable images. Zero residuals on a verification pass cannot prove complete removal. Review the source images and audit reasons before signing off a file.

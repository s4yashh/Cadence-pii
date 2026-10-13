"""Build the self-contained Colab notebook from the tested package sources."""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parent
PKG = ROOT / "src" / "cadence_pii"


def code(source: str):
    return nbf.v4.new_code_cell(source.strip())


def md(source: str):
    return nbf.v4.new_markdown_cell(source.strip())


def build():
    nb = nbf.v4.new_notebook()
    nb.metadata = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                   "language_info": {"name": "python"}, "colab": {"name": "Cadence_PII_Detection.ipynb"}}
    cells = [
        md("""# Cadence PII Detection — live walkthrough

Upload the three **synthetic teaching artifacts** from the case study. This notebook runs extraction, OCR and PII detection inside the active Python runtime; it makes no document-content API calls. Google Colab is cloud hosted, so uploaded files do leave your computer. If your policy disallows that, run this notebook locally in Jupyter.

Run top to bottom. If setup upgrades Pillow in an already-running Colab session, restart the session and choose Run all again; the installed packages remain in place. Review-required files are withheld from the downstream AI boundary until a person checks the source images and signs off. Redaction is pseudonymisation, and a zero-residual scan does not prove that no PII remains."""),
        code("""import importlib.metadata as metadata
import os, shutil, subprocess, sys
from pathlib import Path
IN_COLAB = 'google.colab' in sys.modules
pillow_loaded_before_install = getattr(sys.modules.get('PIL'), '__version__', None)
if IN_COLAB:
    subprocess.run(['apt-get', 'update', '-qq'], check=True)
    subprocess.run(['apt-get', 'install', '-y', '-qq', 'tesseract-ocr', 'libgl1'], check=True)
    packages = ['docling==2.138.0', 'presidio-analyzer==2.2.364', 'presidio-anonymizer==2.2.364',
                'spacy==3.8.16', 'pymupdf==1.28.2', 'python-docx==1.2.0', 'python-pptx==1.0.2',
                'pytesseract==0.3.13', 'Pillow==12.3.0', 'pandas==3.0.6']
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', *packages], check=True)
    subprocess.run([sys.executable, '-m', 'spacy', 'download', 'en_core_web_lg'], check=True)
    # Colab may have imported an older Pillow before pip upgraded it. Mixed in-memory
    # and on-disk PIL modules can fail with `cannot import name _Ink`.
    stale_pillow_typing = sys.modules.get('PIL._typing')
    if ((pillow_loaded_before_install and pillow_loaded_before_install != metadata.version('Pillow'))
            or (stale_pillow_typing is not None and not hasattr(stale_pillow_typing, '_Ink'))):
        raise RuntimeError('Pillow was upgraded in this session. Choose Runtime > Restart session, then Run all again. Packages are already installed.')
for package in ['docling', 'presidio-analyzer', 'spacy', 'python-pptx', 'pytesseract']:
    print(package, metadata.version(package))
subprocess.run(['tesseract', '--version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
Path('cadence_pii/detect').mkdir(parents=True, exist_ok=True)
Path('cadence_pii/extract').mkdir(parents=True, exist_ok=True)"""),
        md("""## Pipeline implementation

These cells write the exact modules used by the local tests. No separate repository download is needed in Colab."""),
    ]
    for path in sorted(PKG.rglob("*.py")):
        rel = path.relative_to(PKG.parent)
        cells.append(code(f"%%writefile {rel.as_posix()}\n" + path.read_text(encoding="utf-8")))
    cells += [
        code("""# Stop early if Docling cannot be imported in this runtime.
# The pipeline has a safe fallback, but this case study's PDF/DOCX structure results use Docling.
from cadence_pii.extract.docling_ext import _converter
_converter('eng')
print('Docling extractor ready')"""),
        md("""## Upload and inventory

Colab prompts for PDF, DOCX and PPTX. Locally, set `CADENCE_INPUT_DIR` to a folder of supported files, or place the supplied files in `Case Study 2 Supporting Material`. The local path is useful for a privacy-restricted walkthrough."""),
        code("""from IPython.display import display
from cadence_pii.ingest import validate
from cadence_pii.config import DEFAULT
SUPPORTED = {'.pdf', '.docx', '.pptx'}
if IN_COLAB:
    from google.colab import files
    uploaded = files.upload()
    input_dir = Path('cadence_inputs')
    input_dir.mkdir(exist_ok=True)
    for name, contents in uploaded.items():
        safe_name = Path(name).name
        (input_dir / safe_name).write_bytes(contents)
        Path(safe_name).unlink(missing_ok=True)  # remove duplicate left by Colab upload
else:
    input_dir = Path(os.environ.get('CADENCE_INPUT_DIR', 'Case Study 2 Supporting Material'))
paths = sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED)
if not paths:
    raise FileNotFoundError(f'No PDF/DOCX/PPTX files found in {input_dir}')
for path in paths:
    try:
        meta = validate(path, DEFAULT)
        print(path.name, meta['filetype'], meta['size_bytes'], 'bytes')
    except Exception as exc:
        print(path.name, 'validation issue:', type(exc).__name__, str(exc))"""),
        md("""## Extract, detect, redact, verify and gate

The PDF uses layout-aware extraction plus OCR of the full pages and figures. The second OCR reading checks for missed exact PII values. PPTX uses its native shapes; DOCX uses layout extraction plus image OCR. Regex and Presidio findings are merged and replaced with typed placeholders. Any detector failure, unresolved residual or uncertain image extraction stops release."""),
        code("""from cadence_pii.pipeline import run_batch
from cadence_pii.report import summary_table, findings_table
results = run_batch(paths)
display(summary_table(results))
for result in results:
    print('\\n', result.filename, result.status.value)
    if result.document:
        print('inventory:', result.document.inventory)
    print('review reasons:', *result.reasons[:8], sep='\\n  ')
    display(findings_table(result, limit=12))"""),
        md("""## Safe preview and release boundary

`SHOW_RAW` defaults to false. The left column describes the original structure without printing extracted source text; the right column shows a redacted excerpt. The masked findings table above supplies source locators and evidence shapes. Turn on raw preview only in a private session if a reviewer explicitly needs it."""),
        code("""from cadence_pii.gate import ReleaseBlocked, get_clean_text, approve
from cadence_pii.redact import masked_context
SHOW_RAW = False
for result in results:
    print('\\nFILE:', result.filename)
    if result.document:
        print('ORIGINAL:', len(result.document.blocks), 'blocks;', len(result.document.text), 'characters; raw hidden')
        if SHOW_RAW:
            print('RAW PREVIEW:', result.document.text[:600])
    preview = masked_context(result.redacted_text, result.findings[0], width=180) if result.findings else '[no findings; raw hidden]'
    print('MASKED REDACTED PREVIEW:', preview)
    print('VERIFY:', result.verification.get('final', {}), 'STATUS:', result.status.value)
    try:
        clean = get_clean_text(result)
        print('Release boundary: passed;', len(clean), 'redacted characters available')
    except ReleaseBlocked as exc:
        print('Release boundary:', exc)"""),
        md("""## Human sign-off, only after source review

To release a review-required file, inspect every review reason and the original image regions first. Enter a reviewer name and a specific note below, then rerun this cell. Blocked and error files cannot be approved. Signing off does not rerun detection; it records accountable human review of the stated uncertainty."""),
        code("""REVIEWER = ''
REVIEW_NOTE = ''
if REVIEWER.strip() and REVIEW_NOTE.strip():
    for result in results:
        if result.status.value == 'REVIEW_REQUIRED':
            approve(result, REVIEWER, REVIEW_NOTE)
            print(result.filename, 'approved; released chars:', len(get_clean_text(result)))
else:
    print('No sign-off entered; review-required files remain withheld.')"""),
        md("""## Export and cleanup

The ZIP contains redacted text, a masked audit report and `ai_ready` copies for cleared files only. Source uploads are excluded. Keep the archive private: redacted text can still contain OCR misses. The last cell can remove uploaded input copies after you have finished reviewing the source."""),
        code("""from cadence_pii.report import export
out_dir = export(results, 'cadence_outputs')
archive = shutil.make_archive('Cadence_PII_Results', 'zip', root_dir=out_dir)
print('Export:', archive)
if IN_COLAB:
    from google.colab import files
    files.download(archive)"""),
        code("""CLEANUP_UPLOADED_INPUTS = False
if CLEANUP_UPLOADED_INPUTS and IN_COLAB:
    for path in paths:
        path.unlink(missing_ok=True)
    print('Deleted uploaded input copies from this runtime. Restart the runtime to clear in-memory content.')
else:
    print('Input copies retained for review; set CLEANUP_UPLOADED_INPUTS=True to delete Colab copies.')"""),
        md("""## Limits

The annotated sample is small and in-sample. The PDF form photo on page 18 is illegible to OCR. OCR corruption inside an identifier can evade both passes; the second reading catches exact matches only. Vector images may be unreadable. Common-word names can be missed. Review the audit reasons and source images before authorising a downstream model. The notebook has been verified locally; a Colab run is pending."""),
    ]
    nb.cells = cells
    nbf.validate(nb)
    output = ROOT / "Cadence_PII_Detection.ipynb"
    nbf.write(nb, output)
    print(output, len(cells), "cells")


if __name__ == "__main__":
    build()

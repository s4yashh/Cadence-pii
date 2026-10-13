"""Execute Colab notebook cells in-process when the sandbox blocks Jupyter sockets."""
from __future__ import annotations

import contextlib
import io
from pathlib import Path

import nbformat
from IPython.core.interactiveshell import InteractiveShell

root = Path(__file__).resolve().parent
nb = nbformat.read(root / "Cadence_PII_Detection.ipynb", as_version=4)
shell = InteractiveShell.instance()
for index, cell in enumerate(nb.cells, start=1):
    if cell.cell_type != "code":
        continue
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        result = shell.run_cell(cell.source)
    if result.error_before_exec or result.error_in_exec:
        raise RuntimeError(f"notebook cell {index} failed") from (result.error_before_exec or result.error_in_exec)
    print(f"cell {index}: OK")
print("Notebook cells executed locally; Colab-only upload/install/download branches were skipped.")

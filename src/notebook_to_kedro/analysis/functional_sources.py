"""Filesystem frontends for source-independent functional inspection."""

from __future__ import annotations

import hashlib
import io
import tokenize
from pathlib import Path

from notebook_to_kedro.analysis.functional import analyze_functional_blocks
from notebook_to_kedro.exceptions import FunctionalSourceError
from notebook_to_kedro.ir.functional import FunctionalAnalysis, SourceUnit
from notebook_to_kedro.notebook import load_notebook
from notebook_to_kedro.notebook.models import NotebookCellKind

MAX_PYTHON_BYTES = 1024 * 1024


def analyze_functional_blocks_path(
    path: str | Path, *, project_root: str | Path | None = None
) -> FunctionalAnalysis:
    """Inspect explicit functions in a Python file or real Python notebook code cells."""
    source_path = Path(path).resolve()
    root = Path.cwd() if project_root is None else Path(project_root).resolve()
    label = (
        source_path.relative_to(root).as_posix()
        if source_path.is_relative_to(root)
        else source_path.as_posix()
    )
    sources: tuple[SourceUnit, ...]
    if source_path.suffix.lower() == ".py":
        sources = (_python_source(source_path, label),)
    elif source_path.suffix.lower() == ".ipynb":
        notebook = load_notebook(source_path, project_root=root)
        sources = tuple(
            SourceUnit(cell.id, label, "notebook", notebook.content_sha256, cell.source, cell.id)
            for cell in notebook.cells
            if cell.kind is NotebookCellKind.CODE
        )
    else:
        raise FunctionalSourceError("Functional inspection requires a .py or .ipynb source")
    return analyze_functional_blocks(sources)


def _python_source(path: Path, label: str) -> SourceUnit:
    try:
        with path.open("rb") as stream:
            content = stream.read(MAX_PYTHON_BYTES + 1)
    except OSError as error:
        raise FunctionalSourceError(f"Cannot read Python source: {path}") from error
    if len(content) > MAX_PYTHON_BYTES:
        raise FunctionalSourceError(f"Python source exceeds {MAX_PYTHON_BYTES} bytes")
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(content).readline)
        source = content.decode(encoding)
    except (SyntaxError, UnicodeError, LookupError) as error:
        raise FunctionalSourceError(f"Cannot decode Python source: {path}") from error
    return SourceUnit("module", label, "python", hashlib.sha256(content).hexdigest(), source)

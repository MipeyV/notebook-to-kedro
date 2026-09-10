"""Public high-level analysis API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from notebook_to_kedro.analysis import analyze_notebook
from notebook_to_kedro.notebook import load_notebook

if TYPE_CHECKING:
    from pathlib import Path

    from notebook_to_kedro.ir import NotebookFacts


def analyze_notebook_path(
    path: str | Path, *, project_root: str | Path | None = None
) -> NotebookFacts:
    """Load a notebook from disk and return deterministic static analysis facts."""
    return analyze_notebook(load_notebook(path, project_root=project_root))

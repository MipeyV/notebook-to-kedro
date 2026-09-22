"""Public high-level analysis API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from notebook_to_kedro.analysis import analyze_notebook
from notebook_to_kedro.generation import generate_kedro_project
from notebook_to_kedro.notebook import load_notebook
from notebook_to_kedro.reporting import render_conversion_report
from notebook_to_kedro.semantic import (
    DeterministicSemanticPlanner,
    SemanticPlanner,
    validate_conversion_plan,
)

if TYPE_CHECKING:
    from pathlib import Path

    from notebook_to_kedro.ir import ConversionPlan, NotebookFacts


_DEFAULT_SEMANTIC_PLANNER: SemanticPlanner = DeterministicSemanticPlanner()


def analyze_notebook_path(
    path: str | Path, *, project_root: str | Path | None = None
) -> NotebookFacts:
    """Load a notebook from disk and return deterministic static analysis facts."""
    return analyze_notebook(load_notebook(path, project_root=project_root))


def plan_notebook_path(
    path: str | Path,
    *,
    project_root: str | Path | None = None,
    planner: SemanticPlanner | None = None,
) -> ConversionPlan:
    """Load and analyze a notebook path, then create a conversion plan."""
    selected_planner = _DEFAULT_SEMANTIC_PLANNER if planner is None else planner
    return selected_planner.create_plan(analyze_notebook_path(path, project_root=project_root))


__all__ = [
    "analyze_notebook_path",
    "generate_kedro_project",
    "plan_notebook_path",
    "render_conversion_report",
    "validate_conversion_plan",
]

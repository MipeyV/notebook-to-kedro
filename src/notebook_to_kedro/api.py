"""Public high-level analysis API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from notebook_to_kedro.analysis import analyze_notebook
from notebook_to_kedro.exceptions import PlannerConfigurationError
from notebook_to_kedro.generation import generate_kedro_project
from notebook_to_kedro.notebook import load_notebook
from notebook_to_kedro.reporting import render_conversion_report
from notebook_to_kedro.semantic import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    DeterministicSemanticPlanner,
    PlannerMode,
    SemanticPlanner,
    create_semantic_planner,
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


def plan_notebook_path(  # noqa: PLR0913
    path: str | Path,
    *,
    project_root: str | Path | None = None,
    planner: SemanticPlanner | PlannerMode | str | None = None,
    ollama_model: str | None = None,
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL,
    ollama_timeout_seconds: float = DEFAULT_OLLAMA_TIMEOUT_SECONDS,
) -> ConversionPlan:
    """Load and analyze a notebook path, then create a conversion plan."""
    selected_planner = _select_planner(
        planner,
        ollama_model=ollama_model,
        ollama_base_url=ollama_base_url,
        ollama_timeout_seconds=ollama_timeout_seconds,
    )
    return selected_planner.create_plan(analyze_notebook_path(path, project_root=project_root))


def _select_planner(
    planner: SemanticPlanner | PlannerMode | str | None,
    *,
    ollama_model: str | None,
    ollama_base_url: str,
    ollama_timeout_seconds: float,
) -> SemanticPlanner:
    uses_default_configuration = (
        ollama_model is None
        and ollama_base_url == DEFAULT_OLLAMA_BASE_URL
        and ollama_timeout_seconds == DEFAULT_OLLAMA_TIMEOUT_SECONDS
    )
    if planner is None and uses_default_configuration:
        return _DEFAULT_SEMANTIC_PLANNER
    if planner is None or isinstance(planner, str):
        return create_semantic_planner(
            PlannerMode.DETERMINISTIC if planner is None else planner,
            ollama_model=ollama_model,
            ollama_base_url=ollama_base_url,
            ollama_timeout_seconds=ollama_timeout_seconds,
        )
    if not uses_default_configuration:
        raise PlannerConfigurationError(
            "Ollama settings cannot be combined with an injected planner"
        )
    return planner


__all__ = [
    "analyze_notebook_path",
    "create_semantic_planner",
    "generate_kedro_project",
    "plan_notebook_path",
    "render_conversion_report",
    "validate_conversion_plan",
]

"""Unit tests for the semantic planner boundary."""

from pathlib import Path

import pytest

from notebook_to_kedro import analyze_notebook_path, plan_notebook_path
from notebook_to_kedro.exceptions import PlannerConfigurationError
from notebook_to_kedro.ir import ConversionPlan, NotebookFacts
from notebook_to_kedro.semantic import (
    DeterministicSemanticPlanner,
    PlannerMode,
    SemanticPlanner,
    plan_tasks,
)

REFERENCE_NOTEBOOK = Path(__file__).parents[2] / "fixtures" / "notebooks" / "simple_training.ipynb"


class _RecordingPlanner:
    def __init__(self) -> None:
        self.received_facts: NotebookFacts | None = None

    def create_plan(self, facts: NotebookFacts) -> ConversionPlan:
        self.received_facts = facts
        return ConversionPlan(
            schema_version="1.0",
            planner_version="test-planner",
            notebook_path=facts.notebook.path,
            task_candidates=(),
        )


def test_deterministic_semantic_planner_implements_protocol() -> None:
    facts = analyze_notebook_path(REFERENCE_NOTEBOOK)
    planner: SemanticPlanner = DeterministicSemanticPlanner()

    assert planner.create_plan(facts) == plan_tasks(facts)


def test_plan_notebook_path_uses_injected_semantic_planner() -> None:
    planner = _RecordingPlanner()

    plan = plan_notebook_path(REFERENCE_NOTEBOOK, planner=planner)

    assert plan.planner_version == "test-planner"
    assert planner.received_facts is not None
    assert planner.received_facts.notebook.path == plan.notebook_path


def test_plan_notebook_path_accepts_explicit_deterministic_mode() -> None:
    plan = plan_notebook_path(REFERENCE_NOTEBOOK, planner=PlannerMode.DETERMINISTIC)

    assert plan.planner_version == "0.1.0"


def test_plan_notebook_path_rejects_provider_settings_with_injected_planner() -> None:
    with pytest.raises(PlannerConfigurationError, match="injected planner"):
        plan_notebook_path(
            REFERENCE_NOTEBOOK,
            planner=_RecordingPlanner(),
            ollama_model="local-model",
        )


def test_plan_notebook_path_rejects_implicit_ollama_configuration() -> None:
    with pytest.raises(PlannerConfigurationError, match="require planner mode 'hybrid'"):
        plan_notebook_path(REFERENCE_NOTEBOOK, ollama_timeout_seconds=10)

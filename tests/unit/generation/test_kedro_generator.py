"""Unit tests for minimal Kedro project generation."""

import importlib
from pathlib import Path

import pytest

from notebook_to_kedro import generate_kedro_project, plan_notebook_path
from notebook_to_kedro.exceptions import ProjectGenerationError
from notebook_to_kedro.ir import ConversionPlan, TaskCandidate

REFERENCE_NOTEBOOK = Path(__file__).parents[2] / "fixtures" / "notebooks" / "simple_training.ipynb"


def test_generate_kedro_project_writes_importable_reference_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = plan_notebook_path(REFERENCE_NOTEBOOK)
    output_path = tmp_path / "generated"

    created_files = generate_kedro_project(plan, output_path, package_name="generated_reference")

    assert len(created_files) == 8
    pyproject_source = (output_path / "pyproject.toml").read_text(encoding="utf-8")
    assert pyproject_source.startswith("[project]")
    assert '"kedro>=1.5,<2"' in pyproject_source
    assert '"scikit-learn>=1.7,<2"' in pyproject_source
    nodes_source = (
        output_path / "src" / "generated_reference" / "pipelines" / "notebook_pipeline" / "nodes.py"
    ).read_text(encoding="utf-8")
    pipeline_source = (
        output_path
        / "src"
        / "generated_reference"
        / "pipelines"
        / "notebook_pipeline"
        / "pipeline.py"
    ).read_text(encoding="utf-8")

    assert "from sklearn.datasets import load_iris" in nodes_source
    assert "def cell_0003():" in nodes_source
    assert "return iris, df" in nodes_source
    assert "'df__cell_0005'" in pipeline_source

    monkeypatch.syspath_prepend(str(output_path / "src"))
    pipeline_module = importlib.import_module("generated_reference.pipelines.notebook_pipeline")

    pipeline = pipeline_module.create_pipeline()

    assert len(pipeline.nodes) == 6


def test_generate_kedro_project_remaps_redefined_symbol_inputs(tmp_path: Path) -> None:
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/example.ipynb",
        imports=(),
        task_candidates=(
            TaskCandidate(
                id="task-0000",
                name="cell_0000",
                source_cell_ids=("cell-0000",),
                statement_ids=("cell-0000-stmt-0000",),
                inputs=(),
                outputs=("df",),
                source="df = load()",
            ),
            TaskCandidate(
                id="task-0001",
                name="cell_0001",
                source_cell_ids=("cell-0001",),
                statement_ids=("cell-0001-stmt-0000",),
                inputs=("df",),
                outputs=("df",),
                source="df = clean(df)",
            ),
            TaskCandidate(
                id="task-0002",
                name="cell_0002",
                source_cell_ids=("cell-0002",),
                statement_ids=("cell-0002-stmt-0000",),
                inputs=("df",),
                outputs=("result",),
                source="result = summarize(df)",
            ),
        ),
    )

    generate_kedro_project(plan, tmp_path / "generated")

    pipeline_source = (
        tmp_path
        / "generated"
        / "src"
        / "generated_notebook"
        / "pipelines"
        / "notebook_pipeline"
        / "pipeline.py"
    ).read_text(encoding="utf-8")
    assert 'outputs="df__cell_0001"' in pipeline_source
    assert "inputs={'df': 'df__cell_0001'}" in pipeline_source


def test_generate_kedro_project_handles_side_effect_task(tmp_path: Path) -> None:
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/example.ipynb",
        task_candidates=(
            TaskCandidate(
                id="task-0000",
                name="cell_0000",
                source_cell_ids=("cell-0000",),
                statement_ids=("cell-0000-stmt-0000",),
                inputs=(),
                outputs=(),
                source="print('done')",
            ),
        ),
    )

    generate_kedro_project(plan, tmp_path / "generated")

    nodes_source = (
        tmp_path
        / "generated"
        / "src"
        / "generated_notebook"
        / "pipelines"
        / "notebook_pipeline"
        / "nodes.py"
    ).read_text(encoding="utf-8")
    pipeline_source = (
        tmp_path
        / "generated"
        / "src"
        / "generated_notebook"
        / "pipelines"
        / "notebook_pipeline"
        / "pipeline.py"
    ).read_text(encoding="utf-8")
    assert "return None" in nodes_source
    assert "outputs=None" in pipeline_source


def test_generate_kedro_project_rejects_existing_destination(tmp_path: Path) -> None:
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/example.ipynb",
        task_candidates=(),
    )
    output_path = tmp_path / "generated"
    output_path.mkdir()

    with pytest.raises(ProjectGenerationError, match="Destination already exists"):
        generate_kedro_project(plan, output_path)


def test_generate_kedro_project_rejects_blocked_plan(tmp_path: Path) -> None:
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/example.ipynb",
        task_candidates=(),
        blocking_diagnostic_codes=("PY001",),
    )

    with pytest.raises(ProjectGenerationError, match="blocking diagnostics"):
        generate_kedro_project(plan, tmp_path / "generated")


def test_generate_kedro_project_rejects_invalid_package_name(tmp_path: Path) -> None:
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/example.ipynb",
        task_candidates=(),
    )

    with pytest.raises(ProjectGenerationError, match="Invalid generated package name"):
        generate_kedro_project(plan, tmp_path / "generated", package_name="bad-name")

    with pytest.raises(ProjectGenerationError, match="Invalid generated package name"):
        generate_kedro_project(plan, tmp_path / "generated", package_name="_private")

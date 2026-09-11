"""Unit tests for minimal Kedro project generation."""

import ast
import importlib
from pathlib import Path

import pytest

from notebook_to_kedro import generate_kedro_project, plan_notebook_path
from notebook_to_kedro.exceptions import ProjectGenerationError
from notebook_to_kedro.generation.kedro import generator
from notebook_to_kedro.ir import CatalogDataset, ConversionPlan, ParameterValue, TaskCandidate

REFERENCE_NOTEBOOK = Path(__file__).parents[2] / "fixtures" / "notebooks" / "simple_training.ipynb"
SCALED_NOTEBOOK = Path(__file__).parents[2] / "fixtures" / "notebooks" / "scaled_training.ipynb"


def test_generate_kedro_project_writes_importable_reference_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = plan_notebook_path(REFERENCE_NOTEBOOK)
    output_path = tmp_path / "generated"

    created_files = generate_kedro_project(plan, output_path, package_name="generated_reference")

    assert len(created_files) == 9
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
    assert "def load_data():" in nodes_source
    assert "return iris, df" in nodes_source
    assert "test_size=split_data_test_size" in nodes_source
    assert "random_state=train_model_random_state" in nodes_source
    assert "'df__prepare_features'" in pipeline_source
    assert "'split_data_test_size': 'params:split_data.test_size'" in pipeline_source
    parameters_source = (output_path / "conf" / "base" / "parameters.yml").read_text(
        encoding="utf-8"
    )
    assert "split_data.test_size: 0.2" in parameters_source
    assert "train_model.n_estimators: 100" in parameters_source

    monkeypatch.syspath_prepend(str(output_path / "src"))
    pipeline_module = importlib.import_module("generated_reference.pipelines.notebook_pipeline")

    pipeline = pipeline_module.create_pipeline()

    assert len(pipeline.nodes) == 6


def test_generate_kedro_project_parameterizes_standard_scaler(tmp_path: Path) -> None:
    plan = plan_notebook_path(SCALED_NOTEBOOK)
    output_path = tmp_path / "generated"

    generate_kedro_project(plan, output_path, package_name="generated_scaled")

    nodes_source = (
        output_path / "src" / "generated_scaled" / "pipelines" / "notebook_pipeline" / "nodes.py"
    ).read_text(encoding="utf-8")
    pipeline_source = (
        output_path / "src" / "generated_scaled" / "pipelines" / "notebook_pipeline" / "pipeline.py"
    ).read_text(encoding="utf-8")
    parameters_source = (output_path / "conf" / "base" / "parameters.yml").read_text(
        encoding="utf-8"
    )

    assert "from sklearn.preprocessing import StandardScaler" in nodes_source
    assert (
        "def scale_features(X_train, X_test, scale_features_with_mean, scale_features_with_std):"
        in (nodes_source)
    )
    assert (
        "StandardScaler(with_mean=scale_features_with_mean, with_std=scale_features_with_std)"
        in (nodes_source)
    )
    assert "'scale_features_with_mean': 'params:scale_features.with_mean'" in pipeline_source
    assert "scale_features.with_mean: true" in parameters_source
    assert "scale_features.with_std: true" in parameters_source


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


def test_generate_kedro_project_writes_catalog_datasets(tmp_path: Path) -> None:
    source_csv = tmp_path / "source.csv"
    source_csv.write_text("value\n1\n", encoding="utf-8")
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/example.ipynb",
        catalog_datasets=(
            CatalogDataset(
                name="df",
                type="kedro_datasets.pandas.CSVDataset",
                filepath="data/01_raw/example.csv",
                source_filepath=str(source_csv),
            ),
        ),
        task_candidates=(
            TaskCandidate(
                id="task-0001",
                name="cell_0001",
                source_cell_ids=("cell-0001",),
                statement_ids=("cell-0001-stmt-0000",),
                inputs=("df",),
                outputs=("result",),
                source="result = df",
            ),
        ),
    )

    created_files = generate_kedro_project(plan, tmp_path / "generated")

    catalog_path = tmp_path / "generated" / "conf" / "base" / "catalog.yml"
    assert catalog_path in created_files
    assert tmp_path / "generated" / "data" / "01_raw" / "example.csv" in created_files
    assert catalog_path.read_text(encoding="utf-8") == (
        "df:\n  type: kedro_datasets.pandas.CSVDataset\n  filepath: data/01_raw/example.csv\n"
    )
    assert (tmp_path / "generated" / "data" / "01_raw" / "example.csv").read_text(
        encoding="utf-8"
    ) == "value\n1\n"


def test_generate_kedro_project_writes_supported_parameter_values(tmp_path: Path) -> None:
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/example.ipynb",
        parameters=(
            ParameterValue(
                name="cell_0000.flag",
                value=True,
                function_argument="cell_0000_flag",
                source_cell_id="cell-0000",
            ),
            ParameterValue(
                name="cell_0000.name",
                value="demo",
                function_argument="cell_0000_name",
                source_cell_id="cell-0000",
            ),
            ParameterValue(
                name="cell_0000.none_value",
                value=None,
                function_argument="cell_0000_none_value",
                source_cell_id="cell-0000",
            ),
        ),
        task_candidates=(
            TaskCandidate(
                id="task-0000",
                name="cell_0000",
                source_cell_ids=("cell-0000",),
                statement_ids=("cell-0000-stmt-0000",),
                inputs=(),
                outputs=("result",),
                source="result = func(flag=True, name='demo', none_value=None)",
                parameters=("cell_0000.flag", "cell_0000.name", "cell_0000.none_value"),
            ),
        ),
    )

    generate_kedro_project(plan, tmp_path / "generated")

    parameters_source = (tmp_path / "generated" / "conf" / "base" / "parameters.yml").read_text(
        encoding="utf-8"
    )
    assert parameters_source == (
        "cell_0000.flag: true\ncell_0000.name: 'demo'\ncell_0000.none_value: null\n"
    )


def test_generate_kedro_project_rejects_missing_catalog_source(tmp_path: Path) -> None:
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/example.ipynb",
        catalog_datasets=(
            CatalogDataset(
                name="df",
                type="kedro_datasets.pandas.CSVDataset",
                filepath="data/01_raw/missing.csv",
                source_filepath=str(tmp_path / "missing.csv"),
            ),
        ),
        task_candidates=(),
    )

    with pytest.raises(ProjectGenerationError, match="Catalog source file does not exist"):
        generate_kedro_project(plan, tmp_path / "generated")


def test_generate_kedro_project_allows_catalog_without_source_copy(tmp_path: Path) -> None:
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/example.ipynb",
        catalog_datasets=(
            CatalogDataset(
                name="df",
                type="kedro_datasets.pandas.CSVDataset",
                filepath="data/01_raw/example.csv",
            ),
        ),
        task_candidates=(),
    )

    created_files = generate_kedro_project(plan, tmp_path / "generated")

    assert tmp_path / "generated" / "conf" / "base" / "catalog.yml" in created_files
    assert tmp_path / "generated" / "data" / "01_raw" / "example.csv" not in created_files


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


def test_generator_ast_helper_fallbacks_cover_uncommon_shapes() -> None:
    assert generator._qualified_name(ast.Constant(value=1)) == "Constant"
    assert generator._offset("value = 1", None, 0) == 0
    assert generator._offset("value = 1", 1, None) == 0

"""Integration tests for loading and statically analyzing the reference notebook."""

from pathlib import Path

from notebook_to_kedro import analyze_notebook_path, plan_notebook_path
from notebook_to_kedro.analysis import analyze_notebook
from notebook_to_kedro.ir import CellKind
from notebook_to_kedro.notebook import load_notebook

REFERENCE_NOTEBOOK = Path(__file__).parents[1] / "fixtures" / "notebooks" / "simple_training.ipynb"
FILE_BACKED_NOTEBOOK = (
    Path(__file__).parents[1] / "fixtures" / "notebooks" / "file_backed_training.ipynb"
)
SCALED_NOTEBOOK = Path(__file__).parents[1] / "fixtures" / "notebooks" / "scaled_training.ipynb"


def test_reference_notebook_static_analysis_extracts_reviewed_facts() -> None:
    """The reference notebook can be loaded and analyzed without execution."""
    loaded_notebook = load_notebook(REFERENCE_NOTEBOOK)
    facts = analyze_notebook(loaded_notebook)
    code_cells = [cell for cell in facts.cells if cell.kind is CellKind.CODE]
    symbols = {symbol.name: symbol for symbol in facts.symbols}

    assert len(facts.cells) == 12
    assert len(code_cells) == 7
    dependency_symbols = {dependency.symbol for dependency in facts.dependencies}
    assert facts.notebook.path == "tests/fixtures/notebooks/simple_training.ipynb"
    assert {"load_iris", "train_test_split", "RandomForestClassifier"} <= symbols.keys()
    assert {"df", "X", "y", "X_train", "model", "predictions", "accuracy"} <= symbols.keys()
    assert {
        "df",
        "X",
        "y",
        "X_train",
        "y_train",
        "model",
        "X_test",
        "predictions",
    } <= dependency_symbols
    assert "DF003" in {diagnostic.code for diagnostic in facts.diagnostics}
    assert any(call.qualified_name == "model.fit" for cell in code_cells for call in cell.calls)


def test_public_api_analyzes_reference_notebook_path() -> None:
    """The package-level API loads and analyzes a notebook path."""
    facts = analyze_notebook_path(REFERENCE_NOTEBOOK)

    assert facts.notebook.path == "tests/fixtures/notebooks/simple_training.ipynb"
    assert len(facts.cells) == 12
    assert any(dependency.symbol == "model" for dependency in facts.dependencies)


def test_public_api_plans_reference_notebook_tasks() -> None:
    """The package-level planning API proposes deterministic task candidates."""
    plan = plan_notebook_path(REFERENCE_NOTEBOOK)

    assert tuple(task.name for task in plan.task_candidates) == (
        "load_data",
        "prepare_features",
        "split_data",
        "train_model",
        "predict",
        "evaluate_model",
    )
    assert plan.task_candidates[0].outputs == ("iris", "df")
    assert plan.task_candidates[1].inputs == ("df",)
    assert plan.task_candidates[-1].inputs == ("y_test", "predictions")
    assert plan.task_candidates[-1].outputs == ("accuracy",)
    assert plan.blocking_diagnostic_codes == ()


def test_public_api_plans_file_backed_notebook_catalog_input() -> None:
    """A CSV-loading notebook produces a catalog input instead of a load node."""
    plan = plan_notebook_path(FILE_BACKED_NOTEBOOK)

    assert tuple(dataset.name for dataset in plan.catalog_datasets) == ("df",)
    assert plan.catalog_datasets[0].filepath == "data/01_raw/binary_classification.csv"
    assert (
        plan.catalog_datasets[0].source_filepath
        == "tests/fixtures/tabular/raw/binary_classification.csv"
    )
    assert tuple(task.name for task in plan.task_candidates) == (
        "prepare_features",
        "split_data",
        "train_model",
        "predict",
        "evaluate_model",
    )
    assert plan.task_candidates[0].inputs == ("df",)
    assert plan.task_candidates[-1].outputs == ("accuracy",)


def test_public_api_plans_scaled_notebook_transform_step() -> None:
    """A notebook with sklearn preprocessing produces an explicit scaling task."""
    plan = plan_notebook_path(SCALED_NOTEBOOK)

    assert tuple(task.name for task in plan.task_candidates) == (
        "load_data",
        "prepare_features",
        "split_data",
        "scale_features",
        "train_model",
        "predict",
        "evaluate_model",
    )
    scaling_task = plan.task_candidates[3]
    assert scaling_task.inputs == ("X_train", "X_test")
    assert scaling_task.outputs == ("scaler", "X_train_scaled", "X_test_scaled")
    assert scaling_task.parameters == (
        "scale_features.with_mean",
        "scale_features.with_std",
    )
    assert tuple(parameter.name for parameter in plan.parameters) == (
        "split_data.test_size",
        "split_data.random_state",
        "scale_features.with_mean",
        "scale_features.with_std",
        "train_model.n_estimators",
        "train_model.random_state",
    )

"""Unit tests for deterministic task planning."""

from notebook_to_kedro.analysis import analyze_notebook
from notebook_to_kedro.notebook import LoadedCell, LoadedNotebook, NotebookCellKind
from notebook_to_kedro.semantic import plan_tasks

SHA256 = "a" * 64


def _loaded_notebook(*cells: LoadedCell) -> LoadedNotebook:
    return LoadedNotebook(
        path="tests/fixtures/notebooks/example.ipynb",
        nbformat=4,
        nbformat_minor=5,
        language="python",
        kernel_name="python3",
        content_sha256=SHA256,
        cells=cells,
    )


def _code_cell(source: str, index: int) -> LoadedCell:
    return LoadedCell(
        id=f"cell-{index:04d}",
        index=index,
        kind=NotebookCellKind.CODE,
        source=source,
    )


def test_plan_tasks_creates_code_cell_candidates_with_data_flow() -> None:
    facts = analyze_notebook(
        _loaded_notebook(
            _code_cell("import pandas as pd", index=0),
            LoadedCell("cell-0001", 1, NotebookCellKind.MARKDOWN, "## Prepare"),
            _code_cell("raw = 1", index=2),
            _code_cell("clean = raw + external", index=3),
        )
    )

    plan = plan_tasks(facts)

    assert plan.schema_version == "1.0"
    assert plan.planner_version == "0.1.0"
    assert plan.notebook_path == "tests/fixtures/notebooks/example.ipynb"
    assert tuple(task.id for task in plan.task_candidates) == ("task-0002", "task-0003")
    assert tuple(task.name for task in plan.task_candidates) == ("prepare", "prepare_2")
    assert plan.task_candidates[0].inputs == ()
    assert plan.task_candidates[0].outputs == ("raw",)
    assert plan.task_candidates[1].source_cell_ids == ("cell-0003",)
    assert plan.task_candidates[1].statement_ids == ("cell-0003-stmt-0000",)
    assert plan.task_candidates[1].inputs == ("raw", "external")
    assert plan.task_candidates[1].outputs == ("clean",)
    assert plan.task_candidates[1].diagnostic_codes == ("DF001",)
    assert plan.blocking_diagnostic_codes == ()


def test_plan_tasks_extracts_supported_literal_parameters() -> None:
    facts = analyze_notebook(
        _loaded_notebook(
            _code_cell("X = 1\ny = 2", index=0),
            _code_cell(
                "\n".join(
                    (
                        "X_train, X_test, y_train, y_test = train_test_split(",
                        "    X, y, test_size=0.25, random_state=42",
                        ")",
                    )
                ),
                index=1,
            ),
            _code_cell(
                "model = RandomForestClassifier(n_estimators=50, random_state=42)",
                index=2,
            ),
        )
    )

    plan = plan_tasks(facts)

    assert tuple(parameter.name for parameter in plan.parameters) == (
        "split_data.test_size",
        "split_data.random_state",
        "train_model.n_estimators",
        "train_model.random_state",
    )
    assert tuple(parameter.value for parameter in plan.parameters) == (0.25, 42, 50, 42)
    assert plan.parameters[0].function_argument == "split_data_test_size"
    assert plan.task_candidates[1].parameters == (
        "split_data.test_size",
        "split_data.random_state",
    )
    assert plan.task_candidates[2].parameters == (
        "train_model.n_estimators",
        "train_model.random_state",
    )


def test_plan_tasks_stops_on_blocking_diagnostics() -> None:
    facts = analyze_notebook(_loaded_notebook(_code_cell("%matplotlib inline", index=0)))

    plan = plan_tasks(facts)

    assert plan.task_candidates == ()
    assert plan.blocking_diagnostic_codes == ("PY002",)


def test_plan_tasks_promotes_csv_loader_to_catalog_dataset() -> None:
    facts = analyze_notebook(
        _loaded_notebook(
            _code_cell("import pandas as pd", index=0),
            _code_cell('df = pd.read_csv("../data/raw/example.csv")', index=1),
            _code_cell('result = df["target"]', index=2),
        )
    )

    plan = plan_tasks(facts)

    assert tuple(dataset.name for dataset in plan.catalog_datasets) == ("df",)
    assert plan.catalog_datasets[0].type == "kedro_datasets.pandas.CSVDataset"
    assert plan.catalog_datasets[0].filepath == "data/01_raw/example.csv"
    assert plan.catalog_datasets[0].source_filepath == "tests/fixtures/data/raw/example.csv"
    assert tuple(task.name for task in plan.task_candidates) == ("cell_0002",)
    assert plan.task_candidates[0].inputs == ("df",)
    assert plan.task_candidates[0].outputs == ("result",)


def test_plan_tasks_uses_source_patterns_before_markdown_headings() -> None:
    facts = analyze_notebook(
        _loaded_notebook(
            LoadedCell("cell-0000", 0, NotebookCellKind.MARKDOWN, "## Prepare features"),
            _code_cell("X = df.drop(columns=['target'])\ny = df['target']", index=1),
            _code_cell("X_train, X_test, y_train, y_test = train_test_split(X, y)", index=2),
        )
    )

    plan = plan_tasks(facts)

    assert tuple(task.name for task in plan.task_candidates) == (
        "prepare_features",
        "split_data",
    )


def test_plan_tasks_normalizes_markdown_headings_to_identifiers() -> None:
    facts = analyze_notebook(
        _loaded_notebook(
            LoadedCell("cell-0000", 0, NotebookCellKind.MARKDOWN, "plain notes"),
            _code_cell("fallback = 1", index=1),
            LoadedCell("cell-0002", 2, NotebookCellKind.MARKDOWN, "## !!!"),
            _code_cell("empty_slug = fallback + 1", index=3),
            LoadedCell("cell-0004", 4, NotebookCellKind.MARKDOWN, "intro\n## 2026 Train"),
            _code_cell("numbered = empty_slug + 1", index=5),
        )
    )

    plan = plan_tasks(facts)

    assert tuple(task.name for task in plan.task_candidates) == (
        "cell_0001",
        "task",
        "task_2026_train",
    )


def test_plan_tasks_preserves_absolute_csv_source_path() -> None:
    facts = analyze_notebook(
        _loaded_notebook(
            _code_cell("import pandas as pd", index=0),
            _code_cell('df = pd.read_csv("/tmp/source.csv")', index=1),
        )
    )

    plan = plan_tasks(facts)

    assert plan.catalog_datasets[0].filepath == "data/01_raw/source.csv"
    assert plan.catalog_datasets[0].source_filepath == "/tmp/source.csv"


def test_plan_tasks_ignores_non_literal_and_non_primitive_parameters() -> None:
    facts = analyze_notebook(
        _loaded_notebook(
            _code_cell("size = 0.2", index=0),
            _code_cell(
                "X_train, X_test, y_train, y_test = train_test_split("
                "X, y, test_size=size, random_state=[42])",
                index=1,
            ),
        )
    )

    plan = plan_tasks(facts)

    assert plan.parameters == ()

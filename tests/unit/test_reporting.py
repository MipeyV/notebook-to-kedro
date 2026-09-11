"""Unit tests for conversion plan reporting."""

from notebook_to_kedro import render_conversion_report
from notebook_to_kedro.ir import CatalogDataset, ConversionPlan, ParameterValue, TaskCandidate


def test_render_conversion_report_summarizes_reviewable_plan() -> None:
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/model.ipynb",
        catalog_datasets=(
            CatalogDataset(
                name="df",
                type="kedro_datasets.pandas.CSVDataset",
                filepath="data/01_raw/example.csv",
                source_filepath="data/raw/example.csv",
            ),
        ),
        parameters=(
            ParameterValue(
                name="split_data.test_size",
                value=0.2,
                function_argument="split_data_test_size",
                source_cell_id="cell-0003",
            ),
        ),
        task_candidates=(
            TaskCandidate(
                id="task-0003",
                name="split_data",
                source_cell_ids=("cell-0003",),
                statement_ids=("cell-0003-stmt-0000",),
                inputs=("X", "y"),
                outputs=("X_train", "X_test", "y_train", "y_test"),
                source="X_train, X_test, y_train, y_test = train_test_split(X, y)",
                parameters=("split_data.test_size",),
                diagnostic_codes=("DF003",),
            ),
        ),
    )

    report = render_conversion_report(plan)

    assert report == (
        "# Notebook to Kedro Conversion Report\n"
        "\n"
        "## Summary\n"
        "- Notebook: `notebooks/model.ipynb`\n"
        "- Schema version: `1.0`\n"
        "- Planner version: `0.1.0`\n"
        "- Status: `ready`\n"
        "- Task candidates: `1`\n"
        "- Catalog datasets: `1`\n"
        "- Parameters: `1`\n"
        "\n"
        "## Task Candidates\n"
        "| Node | Source cells | Inputs | Outputs | Parameters | Diagnostics |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| `split_data` | `cell-0003` | `X`, `y` | `X_train`, `X_test`, `y_train`, "
        "`y_test` | `split_data.test_size` | `DF003` |\n"
        "\n"
        "## Catalog Datasets\n"
        "| Name | Type | Filepath | Source filepath |\n"
        "| --- | --- | --- | --- |\n"
        "| `df` | `kedro_datasets.pandas.CSVDataset` | `data/01_raw/example.csv` | "
        "`data/raw/example.csv` |\n"
        "\n"
        "## Parameters\n"
        "| Name | Value | Function argument | Source cell |\n"
        "| --- | --- | --- | --- |\n"
        "| `split_data.test_size` | `0.2` | `split_data_test_size` | `cell-0003` |\n"
        "\n"
        "## Blocking Diagnostics\n"
        "- None\n"
    )


def test_render_conversion_report_handles_blocked_empty_plan() -> None:
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/broken.ipynb",
        task_candidates=(),
        blocking_diagnostic_codes=("PY002",),
    )

    report = render_conversion_report(plan)

    assert "- Status: `blocked`" in report
    assert "| None | None | None | None | None | None |" in report
    assert "| None | None | None | None |" in report
    assert "- `PY002`" in report


def test_render_conversion_report_handles_task_with_empty_fields() -> None:
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/model.ipynb",
        task_candidates=(
            TaskCandidate(
                id="task-0001",
                name="notify",
                source_cell_ids=("cell-0001",),
                statement_ids=("cell-0001-stmt-0000",),
                inputs=(),
                outputs=(),
                source="print('done')",
            ),
        ),
    )

    report = render_conversion_report(plan)

    assert "| `notify` | `cell-0001` | None | None | None | None |" in report


def test_render_conversion_report_escapes_markdown_table_values() -> None:
    plan = ConversionPlan(
        schema_version="1.0",
        planner_version="0.1.0",
        notebook_path="notebooks/model.ipynb",
        catalog_datasets=(
            CatalogDataset(
                name="raw|data",
                type="custom.Dataset",
                filepath="data\\raw\\example.csv",
            ),
        ),
        parameters=(
            ParameterValue(
                name="task.flag",
                value=True,
                function_argument="task_flag",
                source_cell_id="cell-0001\ncontinued",
            ),
            ParameterValue(
                name="task.optional",
                value=None,
                function_argument="task_optional",
                source_cell_id="cell-0001",
            ),
        ),
        task_candidates=(),
    )

    report = render_conversion_report(plan)

    assert "`raw\\|data`" in report
    assert "`data\\\\raw\\\\example.csv`" in report
    assert "| `task.flag` | `true` | `task_flag` | `cell-0001 continued` |" in report
    assert "| `task.optional` | `null` | `task_optional` | `cell-0001` |" in report

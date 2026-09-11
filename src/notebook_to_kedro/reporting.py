"""Reviewable conversion plan reports."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from notebook_to_kedro.ir import CatalogDataset, ConversionPlan, ParameterValue, TaskCandidate


def render_conversion_report(plan: ConversionPlan) -> str:
    """Render a deterministic Markdown review report for a conversion plan."""
    sections = [
        "# Notebook to Kedro Conversion Report",
        _summary(plan),
        _tasks(plan.task_candidates),
        _catalog_datasets(plan.catalog_datasets),
        _parameters(plan.parameters),
        _blocking_diagnostics(plan.blocking_diagnostic_codes),
    ]
    return "\n\n".join(section for section in sections if section).rstrip() + "\n"


def _summary(plan: ConversionPlan) -> str:
    status = "blocked" if plan.blocking_diagnostic_codes else "ready"
    lines = [
        "## Summary",
        f"- Notebook: `{plan.notebook_path}`",
        f"- Schema version: `{plan.schema_version}`",
        f"- Planner version: `{plan.planner_version}`",
        f"- Status: `{status}`",
        f"- Task candidates: `{len(plan.task_candidates)}`",
        f"- Catalog datasets: `{len(plan.catalog_datasets)}`",
        f"- Parameters: `{len(plan.parameters)}`",
    ]
    return "\n".join(lines)


def _tasks(tasks: tuple[TaskCandidate, ...]) -> str:
    lines = [
        "## Task Candidates",
        "| Node | Source cells | Inputs | Outputs | Parameters | Diagnostics |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if not tasks:
        lines.append("| None | None | None | None | None | None |")
        return "\n".join(lines)
    lines.extend(_task_row(task) for task in tasks)
    return "\n".join(lines)


def _task_row(task: TaskCandidate) -> str:
    return (
        f"| `{_escape_table_text(task.name)}` "
        f"| {_code_list(task.source_cell_ids)} "
        f"| {_code_list(task.inputs)} "
        f"| {_code_list(task.outputs)} "
        f"| {_code_list(task.parameters)} "
        f"| {_code_list(task.diagnostic_codes)} |"
    )


def _catalog_datasets(datasets: tuple[CatalogDataset, ...]) -> str:
    lines = [
        "## Catalog Datasets",
        "| Name | Type | Filepath | Source filepath |",
        "| --- | --- | --- | --- |",
    ]
    if not datasets:
        lines.append("| None | None | None | None |")
        return "\n".join(lines)
    lines.extend(_catalog_dataset_row(dataset) for dataset in datasets)
    return "\n".join(lines)


def _catalog_dataset_row(dataset: CatalogDataset) -> str:
    return (
        f"| `{_escape_table_text(dataset.name)}` "
        f"| `{_escape_table_text(dataset.type)}` "
        f"| `{_escape_table_text(dataset.filepath)}` "
        f"| {_optional_code(dataset.source_filepath)} |"
    )


def _parameters(parameters: tuple[ParameterValue, ...]) -> str:
    lines = [
        "## Parameters",
        "| Name | Value | Function argument | Source cell |",
        "| --- | --- | --- | --- |",
    ]
    if not parameters:
        lines.append("| None | None | None | None |")
        return "\n".join(lines)
    lines.extend(_parameter_row(parameter) for parameter in parameters)
    return "\n".join(lines)


def _parameter_row(parameter: ParameterValue) -> str:
    return (
        f"| `{_escape_table_text(parameter.name)}` "
        f"| `{_escape_table_text(_parameter_value(parameter.value))}` "
        f"| `{_escape_table_text(parameter.function_argument)}` "
        f"| `{_escape_table_text(parameter.source_cell_id)}` |"
    )


def _blocking_diagnostics(codes: tuple[str, ...]) -> str:
    lines = ["## Blocking Diagnostics"]
    if not codes:
        lines.append("- None")
        return "\n".join(lines)
    lines.extend(f"- `{_escape_table_text(code)}`" for code in codes)
    return "\n".join(lines)


def _code_list(values: tuple[str, ...]) -> str:
    if not values:
        return "None"
    return ", ".join(f"`{_escape_table_text(value)}`" for value in values)


def _optional_code(value: str | None) -> str:
    if value is None:
        return "None"
    return f"`{_escape_table_text(value)}`"


def _parameter_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def _escape_table_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")

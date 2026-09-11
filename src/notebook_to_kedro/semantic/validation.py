"""Validation rules for conversion plans before generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from notebook_to_kedro.exceptions import ConversionPlanValidationError

if TYPE_CHECKING:
    from notebook_to_kedro.ir import ConversionPlan


def validate_conversion_plan(plan: ConversionPlan) -> None:
    """Raise when a conversion plan is not safe to pass to a generator."""
    errors = [
        *_blocking_diagnostic_errors(plan),
        *_duplicate_errors("task ID", tuple(task.id for task in plan.task_candidates)),
        *_duplicate_errors("task name", tuple(task.name for task in plan.task_candidates)),
        *_task_name_errors(plan),
        *_duplicate_errors(
            "catalog dataset name", tuple(dataset.name for dataset in plan.catalog_datasets)
        ),
        *_duplicate_errors(
            "parameter name", tuple(parameter.name for parameter in plan.parameters)
        ),
        *_duplicate_errors(
            "parameter function argument",
            tuple(parameter.function_argument for parameter in plan.parameters),
        ),
        *_task_parameter_errors(plan),
    ]
    if errors:
        raise ConversionPlanValidationError(_message(errors))


def _blocking_diagnostic_errors(plan: ConversionPlan) -> tuple[str, ...]:
    if not plan.blocking_diagnostic_codes:
        return ()
    codes = ", ".join(plan.blocking_diagnostic_codes)
    return (f"blocking diagnostics are present: {codes}",)


def _duplicate_errors(label: str, values: tuple[str, ...]) -> tuple[str, ...]:
    duplicates = tuple(value for index, value in enumerate(values) if value in values[:index])
    return tuple(f"duplicate {label}: {value}" for value in dict.fromkeys(duplicates))


def _task_name_errors(plan: ConversionPlan) -> tuple[str, ...]:
    return tuple(
        f"task name must be a public Python identifier: {task.name}"
        for task in plan.task_candidates
        if not task.name.isidentifier() or task.name.startswith("_")
    )


def _task_parameter_errors(plan: ConversionPlan) -> tuple[str, ...]:
    parameter_names = {parameter.name for parameter in plan.parameters}
    return tuple(
        f"task {task.name} references unknown parameter: {parameter_name}"
        for task in plan.task_candidates
        for parameter_name in task.parameters
        if parameter_name not in parameter_names
    )


def _message(errors: list[str]) -> str:
    if len(errors) == 1:
        return f"Invalid conversion plan: {errors[0]}"
    details = "\n".join(f"- {error}" for error in errors)
    return f"Invalid conversion plan:\n{details}"

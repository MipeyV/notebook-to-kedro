"""Render optional runtime boundaries around source-preserving notebook functions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from notebook_to_kedro.generation.kedro.dataframe_checks import frame_decorator_arguments

if TYPE_CHECKING:
    from notebook_to_kedro.generation.kedro.generator import _PipelineEntry
    from notebook_to_kedro.generation.kedro.node_types import NotebookTypeContract

RUNTIME_CHECK_SOURCE = '''"""Optional generated dataset class checks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import wraps
from inspect import signature
from typing import ParamSpec, TypeVar

_P = ParamSpec("_P")
_R = TypeVar("_R")
_Spec = tuple[str, str, type[object]]


def _check_type(value: object, spec: _Spec, location: str) -> None:
    """Reject incompatible classes without coercion or value inspection."""
    dataset, label, expected = spec
    if expected in (bool, int, float, str):
        valid = type(value) is expected
    else:
        valid = isinstance(value, expected)
    if not valid:
        actual = type(value)
        raise TypeError(
            f"{location} {dataset}: expected {label}; "
            f"received {actual.__module__}.{actual.__qualname__}"
        )


def _check_outputs(result: object, specs: tuple[_Spec | None, ...], location: str) -> None:
    """Check declared return slots while preserving the result object and untyped slots."""
    if not any(spec is not None for spec in specs):
        return
    if len(specs) == 1:
        values = (result,)
    elif isinstance(result, tuple) and len(result) == len(specs):
        values = result
    else:
        raise TypeError(f"{location}: expected tuple of {len(specs)} source outputs")
    for value, spec in zip(values, specs, strict=True):
        if spec is not None:
            _check_type(value, spec, location)


def validate_node(
    *, task_id: str, inputs: Mapping[str, _Spec], outputs: tuple[_Spec | None, ...]
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Prepare optional class enforcement without executing the source function.

    Args:
        task_id: Original task identity used in stable diagnostics.
        inputs: Explicit argument-to-dataset class declarations.
        outputs: Ordered source return slots, with None for undeclared types.

    Returns:
        A decorator preserving the public signature, documentation and return identity.
    """
    input_specs = dict(inputs)
    output_specs = tuple(outputs)

    def decorate(function: Callable[_P, _R]) -> Callable[_P, _R]:
        """Bind the source signature once without calling the function."""
        call_signature = signature(function)

        @wraps(function)
        def checked(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            """Enforce declared boundaries and propagate source exceptions unchanged."""
            bound = call_signature.bind(*args, **kwargs)
            for argument, spec in input_specs.items():
                _check_type(bound.arguments[argument], spec, f"NTV001 {task_id} input")
            result = function(*args, **kwargs)
            _check_outputs(result, output_specs, f"NTV002 {task_id} output")
            return result

        return checked

    return decorate
'''


def _specification(dataset: str, contract: NotebookTypeContract, namespace: str) -> str:
    annotation = contract.annotation(dataset, namespace)
    if annotation is None:
        return "None"
    label = dict(contract.datasets)[dataset]
    return f"({dataset!r}, {label!r}, {annotation})"


def render_type_decorator(
    entry: _PipelineEntry, contract: NotebookTypeContract, namespace: str
) -> str:
    """Render only declared boundaries; untyped nodes retain their original callable."""
    declared = dict(contract.datasets)
    inputs = [
        f"{argument!r}: {_specification(dataset, contract, namespace)}"
        for argument, dataset in entry.inputs.items()
        if dataset in declared
    ]
    outputs = [_specification(dataset, contract, namespace) for dataset in entry.outputs]
    if not inputs and all(value == "None" for value in outputs):
        return ""
    output_tuple = "(" + ", ".join(outputs) + (",)" if outputs else ")")
    return (
        f"@{namespace}_validate(\n"
        f"    task_id={entry.task.id!r}, inputs={{{', '.join(inputs)}}},\n"
        f"    outputs={output_tuple},\n"
        + ("" if not contract.dataframes else frame_decorator_arguments(entry, contract))
        + ")\n"
    )


def runtime_check_policy(
    entries: tuple[_PipelineEntry, ...], contract: NotebookTypeContract
) -> dict[str, object]:
    """Describe prepared checks without promoting them to execution evidence."""
    declared = dict(contract.datasets)
    policy: dict[str, object] = {
        "enabled": True,
        "implementation": "node-types-runtime-v1",
        "scope": "declared_dataset_classes",
        "scalar_policy": "exact_builtin",
        "object_policy": "isinstance",
        "source_assertions": "preserved",
        "checked_tasks": [
            entry.task.id
            for entry in entries
            if any(dataset in declared for dataset in (*entry.inputs.values(), *entry.outputs))
        ],
    }
    if contract.dataframes:
        policy.update(
            implementation="node-types-runtime-v2",
            scope="declared_dataset_classes_and_dataframe_metadata",
            dataframe_policy={
                "columns": "unique_flat_strings",
                "order": "declared_projection",
                "extra_columns": "per_declaration",
                "dtypes": "exact_dtype_string",
                "datasets": [name for name, _ in contract.dataframes],
            },
            schema_checked_tasks=[
                entry.task.id
                for entry in entries
                if any(
                    dataset in dict(contract.dataframes)
                    for dataset in (*entry.inputs.values(), *entry.outputs)
                )
            ],
        )
    return policy

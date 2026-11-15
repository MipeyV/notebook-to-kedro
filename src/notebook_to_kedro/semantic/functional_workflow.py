"""Source-accounted ordered workflow wiring, separate from notebook conversion facts."""

from __future__ import annotations

import ast
import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, cast

from notebook_to_kedro.analysis.functional import analyze_functional_blocks
from notebook_to_kedro.exceptions import FunctionalWorkflowError
from notebook_to_kedro.ir.functional import BlockSpan

if TYPE_CHECKING:
    from notebook_to_kedro.ir.file_inputs import FileReferenceInventory
    from notebook_to_kedro.ir.functional import FunctionalAnalysis, FunctionalBlock
    from notebook_to_kedro.ir.source_package import SourcePackage
    from notebook_to_kedro.semantic.functional_config import FunctionalWorkflowConfiguration


@dataclass(frozen=True, slots=True)
class FunctionalWorkflowStep:
    """One original entrypoint call with explicit argument-to-value bindings."""

    id: str
    name: str
    function: str
    inputs: tuple[tuple[str, str], ...]
    output: str
    source: str
    span: BlockSpan


@dataclass(frozen=True, slots=True)
class FunctionalWorkflowPlan:
    """Recomputed inspection and entrypoint wiring; no execution evidence."""

    analysis: FunctionalAnalysis
    configuration: FunctionalWorkflowConfiguration
    steps: tuple[FunctionalWorkflowStep, ...]
    source_package: SourcePackage | None = None
    file_inputs: tuple[FileReferenceInventory, ...] = ()

    @property
    def order_after(self) -> tuple[tuple[str, str], ...]:
        """Declare missing adjacent-call dependencies in the explicit source-order mode."""
        if self.configuration.schema_version not in ("1.2", "1.3", "1.4"):
            return ()
        return tuple(
            (current.id, previous.id)
            for previous, current in zip(self.steps, self.steps[1:], strict=False)
            if previous.output not in {value for _, value in current.inputs}
        )

    def to_json(self) -> str:
        """Export source, I/O decisions and exact step locations for review."""
        payload = {
            "schema_version": "1.0",
            "analysis": json.loads(self.analysis.to_json()),
            "configuration": self.configuration.to_dict(),
            "steps": [asdict(step) for step in self.steps],
        }
        if self.configuration.schema_version in ("1.2", "1.3", "1.4"):
            payload["schema_version"] = "1.1"
            payload["ordering"] = {
                "policy": "source_order",
                "after": [
                    {"step_id": step, "after_step_id": previous}
                    for step, previous in self.order_after
                ],
            }
        if self.source_package is not None:
            payload["schema_version"] = "1.2"
            payload["source_package"] = self.source_package.to_dict()
            payload["source_package_sha256"] = self.source_package.sha256
        if self.configuration.schema_version == "1.4":
            payload["schema_version"] = "1.3"
            payload["file_inputs"] = [item.to_dict() for item in self.file_inputs]
        return json.dumps(payload, sort_keys=True, indent=2) + "\n"


def _call_arguments(call: ast.Call, function: FunctionalBlock) -> tuple[tuple[str, str], ...]:
    if any(not isinstance(value, ast.Name) for value in call.args) or any(
        item.arg is None or not isinstance(item.value, ast.Name) for item in call.keywords
    ):
        raise FunctionalWorkflowError(
            "Workflow calls require named values, without expansion or expressions"
        )
    names = (*function.parameters[: len(call.args)], *(item.arg for item in call.keywords))
    if (
        len(call.args) > len(function.parameters)
        or len(names) != len(set(names))
        or set(names) != set(function.parameters)
    ):
        raise FunctionalWorkflowError(
            "Workflow call arguments must match the called function exactly"
        )
    values = [cast("ast.Name", value).id for value in call.args]
    values.extend(cast("ast.Name", item.value).id for item in call.keywords)
    return tuple((cast("str", name), value) for name, value in zip(names, values, strict=True))


def _step(
    statement: ast.stmt, entry: FunctionalBlock, functions: dict[str, FunctionalBlock], index: int
) -> FunctionalWorkflowStep:
    if not (
        isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id in functions
        and statement.value.func.id != entry.name
    ):
        raise FunctionalWorkflowError(
            "Entrypoint body must assign direct module-function calls to single names"
        )
    function = functions[statement.value.func.id]
    output = statement.targets[0].id
    if not output.isascii() or output.startswith("_") or output == "parameters":
        raise FunctionalWorkflowError("Workflow outputs require public ASCII identifiers")
    return FunctionalWorkflowStep(
        f"{entry.id}:body-{index:04d}",
        f"step_{index:04d}_{function.name}",
        function.name,
        _call_arguments(statement.value, function),
        output,
        cast("str", ast.get_source_segment(entry.source, statement)),
        BlockSpan(
            entry.span.unit_id,
            entry.span.start_line + statement.lineno - 1,
            entry.span.start_line + cast("int", statement.end_lineno) - 1,
            statement.col_offset,
            cast("int", statement.end_col_offset),
        ),
    )


def _validate_package_context(
    analysis: FunctionalAnalysis,
    configuration: FunctionalWorkflowConfiguration,
    source_package: SourcePackage | None,
) -> None:
    if configuration.source_package is not None:
        if (
            source_package is None
            or source_package.root != configuration.source_package
            or analysis.package_module != source_package.module
            or len(analysis.sources) != 1
            or not any(
                item.path == source_package.source_file
                and item.sha256 == analysis.sources[0].document_sha256
                for item in source_package.files
            )
        ):
            raise FunctionalWorkflowError(
                "Workflow requires matching captured source package context"
            )
    elif source_package is not None or analysis.package_module is not None:
        raise FunctionalWorkflowError(
            "Package context requires explicit source_package configuration"
        )


def plan_functional_workflow(
    analysis: FunctionalAnalysis,
    configuration: FunctionalWorkflowConfiguration,
    *,
    source_package: SourcePackage | None = None,
    file_inputs: tuple[FileReferenceInventory, ...] = (),
) -> FunctionalWorkflowPlan:
    """Recompute facts and require single-use data flow with explicit call-order semantics."""
    _validate_package_context(analysis, configuration, source_package)
    if tuple(
        (item.argument, tuple(file.path for file in item.files)) for item in file_inputs
    ) != tuple((name, (value.path, *value.sidecars)) for name, value in configuration.file_inputs):
        raise FunctionalWorkflowError("Workflow requires matching captured file references")
    if (
        analysis
        != analyze_functional_blocks(analysis.sources, package_module=analysis.package_module)
        or not analysis.complete
    ):
        raise FunctionalWorkflowError("Workflow requires complete, recomputed functional analysis")
    functions = {block.name: block for block in analysis.blocks}
    if configuration.entrypoint not in functions:
        raise FunctionalWorkflowError("Configured entrypoint was not found")
    entry = functions[configuration.entrypoint]
    if set(entry.parameters) != set(dict(configuration.inputs)) | set(
        dict(configuration.file_inputs)
    ) | set(dict(configuration.parameters)):
        raise FunctionalWorkflowError(
            "Configured inputs and parameters must cover the entrypoint arguments exactly"
        )
    if entry.outputs != tuple(dict(configuration.outputs)):
        raise FunctionalWorkflowError(
            "Configured output must match the entrypoint's single named return"
        )
    if any(name.startswith("__") for block in analysis.blocks for name in block.global_reads):
        raise FunctionalWorkflowError(
            "Module-identity globals cannot be relocated into a generated project"
        )
    steps = plan_functional_steps(
        entry,
        functions,
        reusable_parameters={
            name for name, value in configuration.parameters if not isinstance(value, tuple)
        },
        source_order=configuration.schema_version in ("1.2", "1.3", "1.4"),
    )
    return FunctionalWorkflowPlan(analysis, configuration, steps, source_package, file_inputs)


def plan_functional_steps(
    entry: FunctionalBlock,
    functions: dict[str, FunctionalBlock],
    *,
    reusable_parameters: set[str],
    source_order: bool,
) -> tuple[FunctionalWorkflowStep, ...]:
    """Validate explicit call wiring, independently of persistent I/O configuration."""
    node = cast("ast.FunctionDef", ast.parse(entry.source).body[0])
    body = node.body[1:] if ast.get_docstring(node) is not None else node.body
    steps = tuple(
        _step(statement, entry, functions, index) for index, statement in enumerate(body[:-1])
    )
    if not steps or steps[-1].output != entry.outputs[0]:
        raise FunctionalWorkflowError("Entrypoint must return the final call result")
    available = set(entry.parameters)
    consumed: set[str] = set()
    previous: str | None = None
    for step in steps:
        values = [value for _, value in step.inputs]
        if set(values) - available or step.output in available:
            raise FunctionalWorkflowError(
                "Workflow needs bound values and distinct single-assignment outputs"
            )
        data_values = [value for value in values if value not in reusable_parameters]
        if len(data_values) != len(set(data_values)) or set(data_values) & consumed:
            raise FunctionalWorkflowError(
                "Data and mapping parameters must be consumed at most once; "
                "aliasing/fan-out is unsupported"
            )
        if not source_order and previous is not None and previous not in data_values:
            raise FunctionalWorkflowError(
                "Every subsequent call must consume the preceding result to preserve order"
            )
        consumed.update(data_values)
        available.add(step.output)
        previous = step.output
    return steps

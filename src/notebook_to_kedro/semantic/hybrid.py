"""Safe assembly of semantic suggestions over deterministic planning evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from notebook_to_kedro.exceptions import (
    ConversionPlanValidationError,
    HybridPlanAssemblyError,
    SemanticPlanningResponseError,
)
from notebook_to_kedro.ir import ConversionPlan, ParameterValue, PlanDiagnostic, TaskCandidate
from notebook_to_kedro.semantic.contracts import (
    SEMANTIC_PLANNING_SCHEMA_VERSION,
    SemanticPlanningRequest,
    SemanticPlanningResult,
    SemanticTaskSuggestion,
)
from notebook_to_kedro.semantic.grouping import has_semantic_merge_candidates
from notebook_to_kedro.semantic.orchestration import request_semantic_planning
from notebook_to_kedro.semantic.planner import plan_tasks
from notebook_to_kedro.semantic.prompting import SEMANTIC_PLANNING_PROMPT_VERSION
from notebook_to_kedro.semantic.suggestion_validation import (
    validate_semantic_planning_response,
)
from notebook_to_kedro.semantic.validation import validate_conversion_plan

if TYPE_CHECKING:
    from collections.abc import Iterable

    from notebook_to_kedro.ir import NotebookFacts
    from notebook_to_kedro.semantic.orchestration import SemanticPlanningFailure
    from notebook_to_kedro.semantic.protocols import SemanticPlanningProvider

HYBRID_PLANNER_VERSION = "0.2.0-hybrid"
DEFAULT_PIPELINE_ID = "notebook_pipeline"


@dataclass(frozen=True, slots=True)
class _SelectedTasks:
    suggestion: SemanticTaskSuggestion
    indexes: tuple[int, ...]
    tasks: tuple[TaskCandidate, ...]


@dataclass(frozen=True, slots=True)
class HybridSemanticPlanner:
    """Use validated provider suggestions with deterministic fallback."""

    provider: SemanticPlanningProvider

    def create_plan(self, facts: NotebookFacts) -> ConversionPlan:
        """Create a hybrid plan or preserve the deterministic baseline on failure."""
        baseline = plan_tasks(facts)
        if baseline.blocking_diagnostic_codes:
            return baseline
        request = SemanticPlanningRequest(
            schema_version=SEMANTIC_PLANNING_SCHEMA_VERSION,
            request_id=f"planning-{facts.notebook.content_sha256[:16]}",
            prompt_version=SEMANTIC_PLANNING_PROMPT_VERSION,
            facts=facts,
            baseline_plan=baseline,
        )
        if not has_semantic_merge_candidates(request):
            return baseline
        outcome = request_semantic_planning(request, self.provider)
        if outcome.result is None:
            failure = cast("SemanticPlanningFailure", outcome.failure)
            return _fallback_plan(
                baseline,
                code=failure.code,
                message=failure.message,
            )
        try:
            return assemble_hybrid_plan(outcome.result)
        except HybridPlanAssemblyError as error:
            return _fallback_plan(
                baseline,
                code="hybrid_assembly_failed",
                message=str(error),
            )


def assemble_hybrid_plan(result: SemanticPlanningResult) -> ConversionPlan:
    """Build and validate a plan while keeping deterministic evidence authoritative."""
    try:
        return _assemble_hybrid_plan(result)
    except (ConversionPlanValidationError, SemanticPlanningResponseError) as error:
        message = f"Cannot assemble hybrid plan: {error}"
        raise HybridPlanAssemblyError(message) from error


def _assemble_hybrid_plan(result: SemanticPlanningResult) -> ConversionPlan:
    request = result.request
    response = result.response
    baseline = request.baseline_plan
    if baseline.blocking_diagnostic_codes:
        raise HybridPlanAssemblyError("Cannot assemble a blocked deterministic plan")
    validate_semantic_planning_response(request, response)
    selections = tuple(
        sorted(
            (_select_baseline_tasks(suggestion, baseline) for suggestion in response.tasks),
            key=lambda selection: selection.indexes[0],
        )
    )
    _require_supported_pipeline_ids(selections)

    task_id_map: dict[str, str] = {}
    parameter_name_map: dict[str, str] = {}
    tasks: list[TaskCandidate] = []
    assistance_diagnostics: list[PlanDiagnostic] = []
    for selection in selections:
        task, adjusted_interface = _assemble_task(selection, parameter_name_map)
        tasks.append(task)
        task_id_map.update({baseline_task.id: task.id for baseline_task in selection.tasks})
        assistance_diagnostics.extend(
            _task_assistance_diagnostics(
                selection.suggestion,
                task,
                adjusted_interface=adjusted_interface,
            )
        )

    parameters = _assembled_parameters(baseline, parameter_name_map)
    diagnostics = (
        *_remapped_baseline_diagnostics(baseline, task_id_map),
        PlanDiagnostic(
            code="SP001",
            severity="info",
            message=(
                "Semantic planning accepted from provider "
                f"{result.trace.provider_name} using model {result.trace.model_name} "
                f"and prompt {result.trace.prompt_version}."
            ),
        ),
        *(
            PlanDiagnostic(code="SP002", severity="warning", message=note)
            for note in response.review_notes
        ),
        *assistance_diagnostics,
    )
    plan = ConversionPlan(
        schema_version=baseline.schema_version,
        planner_version=HYBRID_PLANNER_VERSION,
        notebook_path=baseline.notebook_path,
        task_candidates=tuple(tasks),
        imports=baseline.imports,
        catalog_datasets=baseline.catalog_datasets,
        parameters=parameters,
        diagnostics=diagnostics,
        blocking_diagnostic_codes=baseline.blocking_diagnostic_codes,
    )
    validate_conversion_plan(plan)
    return plan


def _select_baseline_tasks(
    suggestion: SemanticTaskSuggestion, baseline: ConversionPlan
) -> _SelectedTasks:
    suggested_statements = set(suggestion.statement_ids)
    selected: list[tuple[int, TaskCandidate]] = []
    for index, task in enumerate(baseline.task_candidates):
        overlap = suggested_statements.intersection(task.statement_ids)
        if not overlap:
            continue
        if overlap != set(task.statement_ids):
            message = (
                f"task {suggestion.node_name} splits deterministic task {task.name}; "
                "partial task splitting is not supported"
            )
            raise HybridPlanAssemblyError(message)
        selected.append((index, task))
    indexes = tuple(index for index, _ in selected)
    expected_indexes = tuple(range(indexes[0], indexes[-1] + 1))
    if indexes != expected_indexes:
        message = f"task {suggestion.node_name} groups non-contiguous deterministic tasks"
        raise HybridPlanAssemblyError(message)
    return _SelectedTasks(
        suggestion=suggestion,
        indexes=indexes,
        tasks=tuple(task for _, task in selected),
    )


def _require_supported_pipeline_ids(selections: tuple[_SelectedTasks, ...]) -> None:
    unsupported = tuple(
        selection.suggestion.pipeline_id
        for selection in selections
        if selection.suggestion.pipeline_id != DEFAULT_PIPELINE_ID
    )
    if unsupported:
        pipeline_ids = ", ".join(dict.fromkeys(unsupported))
        message = f"unsupported hybrid pipeline IDs: {pipeline_ids}"
        raise HybridPlanAssemblyError(message)


def _assemble_task(
    selection: _SelectedTasks,
    parameter_name_map: dict[str, str],
) -> tuple[TaskCandidate, bool]:
    suggestion = selection.suggestion
    baseline_tasks = selection.tasks
    inputs = _assembled_inputs(baseline_tasks)
    outputs = _ordered_unique(name for task in baseline_tasks for name in task.outputs)
    original_parameter_names = _ordered_unique(
        name for task in baseline_tasks for name in task.parameters
    )
    parameter_suffixes = tuple(
        name.rsplit(".", maxsplit=1)[-1] for name in original_parameter_names
    )
    if len(parameter_suffixes) != len(set(parameter_suffixes)):
        message = f"task {suggestion.node_name} merges conflicting parameter names"
        raise HybridPlanAssemblyError(message)
    renamed_parameters = tuple(f"{suggestion.node_name}.{suffix}" for suffix in parameter_suffixes)
    parameter_name_map.update(zip(original_parameter_names, renamed_parameters, strict=True))
    task = TaskCandidate(
        id=baseline_tasks[0].id,
        name=suggestion.node_name,
        source_cell_ids=_ordered_unique(
            cell_id for baseline_task in baseline_tasks for cell_id in baseline_task.source_cell_ids
        ),
        statement_ids=_ordered_unique(
            statement_id
            for baseline_task in baseline_tasks
            for statement_id in baseline_task.statement_ids
        ),
        inputs=inputs,
        outputs=outputs,
        source="\n".join(task.source.rstrip() for task in baseline_tasks),
        parameters=renamed_parameters,
        diagnostic_codes=_ordered_unique(
            code for baseline_task in baseline_tasks for code in baseline_task.diagnostic_codes
        ),
    )
    adjusted_interface = (
        suggestion.inputs != inputs
        or suggestion.outputs != outputs
        or suggestion.parameter_names != original_parameter_names
    )
    return task, adjusted_interface


def _assembled_inputs(tasks: tuple[TaskCandidate, ...]) -> tuple[str, ...]:
    inputs: list[str] = []
    produced: set[str] = set()
    for task in tasks:
        inputs.extend(name for name in task.inputs if name not in produced and name not in inputs)
        produced.update(task.outputs)
    return tuple(inputs)


def _assembled_parameters(
    baseline: ConversionPlan, parameter_name_map: dict[str, str]
) -> tuple[ParameterValue, ...]:
    missing = tuple(
        parameter.name
        for parameter in baseline.parameters
        if parameter.name not in parameter_name_map
    )
    if missing:
        names = ", ".join(missing)
        raise HybridPlanAssemblyError(f"hybrid tasks did not preserve parameters: {names}")
    return tuple(
        replace(
            parameter,
            name=parameter_name_map[parameter.name],
            function_argument=parameter_name_map[parameter.name].replace(".", "_"),
        )
        for parameter in baseline.parameters
    )


def _remapped_baseline_diagnostics(
    baseline: ConversionPlan, task_id_map: dict[str, str]
) -> tuple[PlanDiagnostic, ...]:
    return tuple(
        replace(
            diagnostic,
            task_id=(
                task_id_map.get(diagnostic.task_id, diagnostic.task_id)
                if diagnostic.task_id is not None
                else None
            ),
        )
        for diagnostic in baseline.diagnostics
    )


def _task_assistance_diagnostics(
    suggestion: SemanticTaskSuggestion,
    task: TaskCandidate,
    *,
    adjusted_interface: bool,
) -> tuple[PlanDiagnostic, ...]:
    diagnostics = [
        PlanDiagnostic(code="SP003", severity="warning", message=note, task_id=task.id)
        for note in suggestion.review_notes
    ]
    if adjusted_interface:
        diagnostics.append(
            PlanDiagnostic(
                code="SP004",
                severity="info",
                message=(
                    f"Task {task.name} uses inputs, outputs, and parameters recomputed from "
                    "deterministic evidence."
                ),
                task_id=task.id,
            )
        )
    return tuple(diagnostics)


def _fallback_plan(baseline: ConversionPlan, *, code: str, message: str) -> ConversionPlan:
    return replace(
        baseline,
        planner_version=f"{HYBRID_PLANNER_VERSION}-fallback",
        diagnostics=(
            *baseline.diagnostics,
            PlanDiagnostic(
                code="SP005",
                severity="warning",
                message=f"Semantic planning fallback ({code}): {message}",
            ),
        ),
    )


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))

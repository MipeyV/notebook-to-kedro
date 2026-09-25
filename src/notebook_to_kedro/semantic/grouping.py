"""Compact provider contract and deterministic semantic-group expansion."""

from __future__ import annotations

import json
import keyword
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from notebook_to_kedro.exceptions import SemanticPlanningResponseError
from notebook_to_kedro.ir import CellKind
from notebook_to_kedro.semantic.contracts import (
    SemanticPlanningResponse,
    SemanticTaskSuggestion,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from notebook_to_kedro.ir import TaskCandidate
    from notebook_to_kedro.semantic.contracts import SemanticPlanningRequest

SEMANTIC_GROUPING_SCHEMA_VERSION = "1.0"
DEFAULT_PIPELINE_ID = "notebook_pipeline"
_GROUP_KEYS = frozenset({"baseline_task_ids"})
_RESPONSE_KEYS = frozenset({"schema_version", "request_id", "groups"})
_HEADING_WORD = re.compile(r"[A-Za-z0-9]+")
_HEADING_STOP_WORDS = frozenset({"a", "an", "the"})


@dataclass(frozen=True, slots=True)
class SemanticTaskGroup:
    """One proposed group of contiguous deterministic task candidates."""

    baseline_task_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.baseline_task_ids:
            raise ValueError("baseline_task_ids must not be empty")
        if any(not task_id for task_id in self.baseline_task_ids):
            raise ValueError("baseline_task_ids must not contain empty values")
        if len(self.baseline_task_ids) != len(set(self.baseline_task_ids)):
            raise ValueError("baseline_task_ids must contain unique values")

    def to_dict(self) -> dict[str, object]:
        """Return the canonical JSON-compatible group payload."""
        return {"baseline_task_ids": list(self.baseline_task_ids)}


@dataclass(frozen=True, slots=True)
class SemanticGroupingResponse:
    """Minimal provider response describing only semantic task boundaries."""

    schema_version: str
    request_id: str
    groups: tuple[SemanticTaskGroup, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SEMANTIC_GROUPING_SCHEMA_VERSION:
            message = f"schema_version must be {SEMANTIC_GROUPING_SCHEMA_VERSION!r}"
            raise ValueError(message)
        if not self.request_id:
            raise ValueError("request_id must not be empty")

    def to_dict(self) -> dict[str, object]:
        """Return the canonical JSON-compatible response payload."""
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "groups": [group.to_dict() for group in self.groups],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize the grouping response deterministically."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=True, sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> Self:
        """Decode and validate a strict grouping response."""
        try:
            decoded: object = json.loads(payload)
            data = _object(decoded, "semantic grouping response")
            _require_exact_keys(data, _RESPONSE_KEYS, "semantic grouping response")
            groups = _groups(data["groups"])
            return cls(
                schema_version=_string(data["schema_version"], "schema_version"),
                request_id=_string(data["request_id"], "request_id"),
                groups=groups,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            message = f"Invalid semantic grouping response: {error}"
            raise SemanticPlanningResponseError(message) from error


def semantic_grouping_response_schema(request: SemanticPlanningRequest) -> dict[str, object]:
    """Build a schema restricted to safe contiguous groups for one request."""
    allowed_groups = [list(group) for group in _allowed_task_id_groups(request)]
    groups_schema: dict[str, object] = {"type": "array", "maxItems": 0}
    if allowed_groups:
        groups_schema = {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["baseline_task_ids"],
                "properties": {
                    "baseline_task_ids": {
                        "type": "array",
                        "enum": allowed_groups,
                    }
                },
            },
        }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "SemanticGroupingResponse",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "request_id", "groups"],
        "properties": {
            "schema_version": {
                "type": "string",
                "const": SEMANTIC_GROUPING_SCHEMA_VERSION,
            },
            "request_id": {"type": "string", "const": request.request_id},
            "groups": groups_schema,
        },
    }


def has_semantic_merge_candidates(request: SemanticPlanningRequest) -> bool:
    """Return whether the request permits at least one non-singleton task group."""
    return any(len(group) > 1 for group in _allowed_task_id_groups(request))


def expand_semantic_grouping(
    request: SemanticPlanningRequest, response: SemanticGroupingResponse
) -> SemanticPlanningResponse:
    """Expand provider-selected task groups using deterministic baseline evidence."""
    if response.request_id != request.request_id:
        raise SemanticPlanningResponseError("grouping response request_id does not match request")
    baseline_tasks = request.baseline_plan.task_candidates
    expected_ids = tuple(task.id for task in baseline_tasks)
    grouped_ids = tuple(task_id for group in response.groups for task_id in group.baseline_task_ids)
    if grouped_ids != expected_ids:
        raise SemanticPlanningResponseError(
            "grouping response must contain every baseline task exactly once in baseline order"
        )
    allowed_groups = frozenset(_allowed_task_id_groups(request))
    if any(group.baseline_task_ids not in allowed_groups for group in response.groups):
        raise SemanticPlanningResponseError(
            "grouping response contains a task group that is not permitted"
        )

    tasks_by_id = {task.id: task for task in baseline_tasks}
    section_contexts = section_contexts_by_cell_id(request)
    suggestions = tuple(
        _expand_group(
            tuple(tasks_by_id[task_id] for task_id in group.baseline_task_ids),
            section_contexts,
        )
        for group in response.groups
    )
    return SemanticPlanningResponse(
        schema_version=request.schema_version,
        request_id=request.request_id,
        tasks=suggestions,
    )


def section_contexts_by_cell_id(
    request: SemanticPlanningRequest,
) -> dict[str, tuple[str, str]]:
    """Map code cells to the nearest preceding Markdown heading identity and text."""
    contexts: dict[str, tuple[str, str]] = {}
    current_section = ("", "")
    for cell in request.facts.cells:
        if cell.kind is CellKind.MARKDOWN:
            heading = _markdown_heading(cell.source)
            if heading is not None:
                current_section = (cell.id, heading)
        else:
            contexts[cell.id] = current_section
    return contexts


def task_section_contexts(
    cell_ids: tuple[str, ...], contexts_by_cell: dict[str, tuple[str, str]]
) -> tuple[tuple[str, str], ...]:
    """Return ordered unique section contexts represented by task source cells."""
    return tuple(
        dict.fromkeys(
            context
            for cell_id in cell_ids
            if (context := contexts_by_cell.get(cell_id, ("", "")))[0]
        )
    )


def _allowed_task_id_groups(request: SemanticPlanningRequest) -> tuple[tuple[str, ...], ...]:
    tasks = request.baseline_plan.task_candidates
    contexts = section_contexts_by_cell_id(request)
    allowed: list[tuple[str, ...]] = []
    for start, first in enumerate(tasks):
        section = task_section_contexts(first.source_cell_ids, contexts)
        task_ids: list[str] = []
        for task in tasks[start:]:
            if task_section_contexts(task.source_cell_ids, contexts) != section:
                break
            if task_ids and len(task.statement_ids) != 1:
                break
            task_ids.append(task.id)
            allowed.append(tuple(task_ids))
            if len(task.statement_ids) != 1:
                break
    return tuple(allowed)


def _expand_group(
    tasks: tuple[TaskCandidate, ...],
    section_contexts: dict[str, tuple[str, str]],
) -> SemanticTaskSuggestion:
    return SemanticTaskSuggestion(
        source_cell_ids=_ordered_unique(
            cell_id for task in tasks for cell_id in task.source_cell_ids
        ),
        statement_ids=_ordered_unique(
            statement_id for task in tasks for statement_id in task.statement_ids
        ),
        node_name=_group_node_name(tasks, section_contexts),
        inputs=_assembled_inputs(tasks),
        outputs=_ordered_unique(name for task in tasks for name in task.outputs),
        parameter_names=_ordered_unique(name for task in tasks for name in task.parameters),
        pipeline_id=DEFAULT_PIPELINE_ID,
    )


def _group_node_name(
    tasks: tuple[TaskCandidate, ...],
    section_contexts: dict[str, tuple[str, str]],
) -> str:
    if len(tasks) == 1:
        return tasks[0].name
    contexts = task_section_contexts(
        _ordered_unique(cell_id for task in tasks for cell_id in task.source_cell_ids),
        section_contexts,
    )
    if len(contexts) == 1:
        words = tuple(
            word.lower()
            for word in _HEADING_WORD.findall(contexts[0][1].lstrip("#"))
            if word.lower() not in _HEADING_STOP_WORDS
        )
        candidate = "_".join(words)
        if candidate and candidate[0].isalpha() and not keyword.iskeyword(candidate):
            return candidate
    return tasks[0].name


def _assembled_inputs(tasks: tuple[TaskCandidate, ...]) -> tuple[str, ...]:
    inputs: list[str] = []
    produced: set[str] = set()
    for task in tasks:
        inputs.extend(name for name in task.inputs if name not in produced and name not in inputs)
        produced.update(task.outputs)
    return tuple(inputs)


def _markdown_heading(source: str) -> str | None:
    return next(
        (line.strip() for line in source.splitlines() if line.lstrip().startswith("#")),
        None,
    )


def _groups(value: object) -> tuple[SemanticTaskGroup, ...]:
    if not isinstance(value, list):
        raise TypeError("groups must be an array")
    groups: list[SemanticTaskGroup] = []
    for value_group in value:
        group = _object(value_group, "semantic task group")
        _require_exact_keys(group, _GROUP_KEYS, "semantic task group")
        groups.append(
            SemanticTaskGroup(
                baseline_task_ids=_string_tuple(group["baseline_task_ids"], "baseline_task_ids")
            )
        )
    return tuple(groups)


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise TypeError(f"{label} must be an object")
    return cast("dict[str, object]", value)


def _require_exact_keys(value: dict[str, object], expected: frozenset[str], label: str) -> None:
    if frozenset(value) != expected:
        raise ValueError(f"{label} fields must be exactly {sorted(expected)}")


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{label} must be an array of strings")
    return tuple(value)


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


__all__ = [
    "SEMANTIC_GROUPING_SCHEMA_VERSION",
    "SemanticGroupingResponse",
    "SemanticTaskGroup",
    "expand_semantic_grouping",
    "has_semantic_merge_candidates",
    "section_contexts_by_cell_id",
    "semantic_grouping_response_schema",
    "task_section_contexts",
]

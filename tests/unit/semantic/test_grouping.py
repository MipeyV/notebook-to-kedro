"""Tests for compact semantic grouping contracts and deterministic expansion."""

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from notebook_to_kedro import analyze_notebook_path, plan_notebook_path
from notebook_to_kedro.exceptions import SemanticPlanningResponseError
from notebook_to_kedro.semantic import (
    SEMANTIC_GROUPING_SCHEMA_VERSION,
    SEMANTIC_PLANNING_PROMPT_VERSION,
    SEMANTIC_PLANNING_SCHEMA_VERSION,
    SemanticGroupingResponse,
    SemanticPlanningRequest,
    SemanticPlanningResponse,
    SemanticTaskGroup,
    expand_semantic_grouping,
    semantic_grouping_response_schema,
)
from notebook_to_kedro.semantic import grouping as grouping_module

CHALLENGE_NOTEBOOK = (
    Path(__file__).parents[2] / "fixtures" / "notebooks" / "statement_split_training.ipynb"
)


def _challenge_request() -> SemanticPlanningRequest:
    facts = analyze_notebook_path(CHALLENGE_NOTEBOOK)
    return SemanticPlanningRequest(
        schema_version=SEMANTIC_PLANNING_SCHEMA_VERSION,
        request_id=f"planning-{facts.notebook.content_sha256[:16]}",
        prompt_version=SEMANTIC_PLANNING_PROMPT_VERSION,
        facts=facts,
        baseline_plan=plan_notebook_path(CHALLENGE_NOTEBOOK),
    )


def test_grouping_response_round_trips_canonical_json(
    semantic_grouping_response: SemanticGroupingResponse,
) -> None:
    payload = semantic_grouping_response.to_json(indent=None)

    assert SemanticGroupingResponse.from_json(payload) == semantic_grouping_response
    assert semantic_grouping_response.to_dict()["groups"] == [
        group.to_dict() for group in semantic_grouping_response.groups
    ]


@pytest.mark.parametrize(
    ("task_ids", "message"),
    [
        ((), "must not be empty"),
        (("",), "must not contain empty"),
        (("task-1", "task-1"), "must contain unique"),
    ],
)
def test_task_group_rejects_invalid_ids(task_ids: tuple[str, ...], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        SemanticTaskGroup(task_ids)


@pytest.mark.parametrize(
    ("schema_version", "request_id", "message"),
    [
        ("2.0", "request", "schema_version"),
        (SEMANTIC_GROUPING_SCHEMA_VERSION, "", "request_id"),
    ],
)
def test_grouping_response_rejects_invalid_identity(
    schema_version: str, request_id: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        SemanticGroupingResponse(schema_version, request_id, ())


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        "[]",
        '{"schema_version":1,"request_id":"request","groups":[]}',
        '{"schema_version":"1.0","request_id":"request"}',
        '{"schema_version":"1.0","request_id":"request","groups":{}}',
        (
            '{"schema_version":"1.0","request_id":"request","groups":'
            '[{"baseline_task_ids":["task-1"],"extra":true}]}'
        ),
        (
            '{"schema_version":"1.0","request_id":"request","groups":'
            '[{"baseline_task_ids":"task-1"}]}'
        ),
    ],
)
def test_grouping_response_rejects_malformed_json(payload: str) -> None:
    with pytest.raises(SemanticPlanningResponseError, match="semantic grouping response"):
        SemanticGroupingResponse.from_json(payload)


def test_grouping_schema_keeps_cohesive_tasks_atomic(
    semantic_request: SemanticPlanningRequest,
) -> None:
    schema = semantic_grouping_response_schema(semantic_request)
    properties = cast("dict[str, object]", schema["properties"])
    groups = cast("dict[str, object]", properties["groups"])
    items = cast("dict[str, object]", groups["items"])
    group_properties = cast("dict[str, object]", items["properties"])
    task_ids = cast("dict[str, object]", group_properties["baseline_task_ids"])
    allowed = cast("list[list[str]]", task_ids["enum"])
    baseline = semantic_request.baseline_plan.task_candidates

    assert properties["request_id"] == {
        "type": "string",
        "const": semantic_request.request_id,
    }
    assert [baseline[1].id] in allowed
    assert [baseline[1].id, baseline[2].id] not in allowed
    assert [baseline[3].id, baseline[4].id] not in allowed
    assert [baseline[0].id, baseline[1].id] not in allowed


def test_grouping_schema_allows_adjacent_single_statement_fragments() -> None:
    request = _challenge_request()
    schema = semantic_grouping_response_schema(request)
    properties = cast("dict[str, object]", schema["properties"])
    groups = cast("dict[str, object]", properties["groups"])
    items = cast("dict[str, object]", groups["items"])
    group_properties = cast("dict[str, object]", items["properties"])
    task_ids = cast("dict[str, object]", group_properties["baseline_task_ids"])
    allowed = cast("list[list[str]]", task_ids["enum"])

    assert ["task-0006", "task-0007", "task-0008"] in allowed
    assert ["task-0008", "task-0010"] not in allowed


def test_allowed_groups_do_not_absorb_a_following_cohesive_task() -> None:
    request = _challenge_request()
    tasks = request.baseline_plan.task_candidates
    cohesive_second = replace(
        tasks[1],
        statement_ids=(*tasks[1].statement_ids, "synthetic-second-statement"),
    )
    request = replace(
        request,
        baseline_plan=replace(
            request.baseline_plan,
            task_candidates=(tasks[0], cohesive_second, *tasks[2:]),
        ),
    )

    allowed = grouping_module._allowed_task_id_groups(request)

    assert (tasks[0].id, tasks[1].id) not in allowed


def test_grouping_schema_supports_an_empty_baseline(
    semantic_request: SemanticPlanningRequest,
) -> None:
    request = replace(
        semantic_request,
        baseline_plan=replace(semantic_request.baseline_plan, task_candidates=()),
    )
    schema = semantic_grouping_response_schema(request)
    properties = cast("dict[str, object]", schema["properties"])

    assert properties["groups"] == {"type": "array", "maxItems": 0}


def test_expansion_preserves_singleton_boundaries(
    semantic_request: SemanticPlanningRequest,
    semantic_response: SemanticPlanningResponse,
    semantic_grouping_response: SemanticGroupingResponse,
) -> None:
    response = expand_semantic_grouping(semantic_request, semantic_grouping_response)

    assert response == replace(semantic_response, review_notes=())


def test_expansion_rejects_wrong_identity_or_incomplete_partition(
    semantic_request: SemanticPlanningRequest,
    semantic_grouping_response: SemanticGroupingResponse,
) -> None:
    with pytest.raises(SemanticPlanningResponseError, match="request_id"):
        expand_semantic_grouping(
            semantic_request,
            replace(semantic_grouping_response, request_id="other-request"),
        )

    with pytest.raises(SemanticPlanningResponseError, match="every baseline task"):
        expand_semantic_grouping(
            semantic_request,
            replace(
                semantic_grouping_response,
                groups=semantic_grouping_response.groups[:-1],
            ),
        )


def test_expansion_rejects_a_group_forbidden_by_the_request_schema(
    semantic_request: SemanticPlanningRequest,
    semantic_grouping_response: SemanticGroupingResponse,
) -> None:
    groups = semantic_grouping_response.groups
    forbidden = SemanticTaskGroup((*groups[0].baseline_task_ids, *groups[1].baseline_task_ids))
    response = replace(
        semantic_grouping_response,
        groups=(forbidden, *groups[2:]),
    )

    with pytest.raises(SemanticPlanningResponseError, match="not permitted"):
        expand_semantic_grouping(semantic_request, response)


def test_expansion_builds_reviewed_challenge_groups() -> None:
    request = _challenge_request()
    response = SemanticGroupingResponse(
        schema_version=SEMANTIC_GROUPING_SCHEMA_VERSION,
        request_id=request.request_id,
        groups=tuple(
            SemanticTaskGroup(task_ids)
            for task_ids in (
                ("task-0003", "task-0004"),
                ("task-0006", "task-0007", "task-0008"),
                ("task-0010",),
                ("task-0012", "task-0013"),
                ("task-0015",),
                ("task-0017", "task-0018", "task-0019"),
            )
        ),
    )

    expanded = expand_semantic_grouping(request, response)

    assert tuple(task.node_name for task in expanded.tasks) == (
        "load_data",
        "prepare_features",
        "split_data",
        "train_model",
        "predict",
        "evaluate_model",
    )
    assert expanded.tasks[1].inputs == ("df",)
    assert expanded.tasks[1].outputs == ("df", "X", "y")
    assert expanded.tasks[3].inputs == ("X_train", "y_train")
    assert expanded.tasks[5].outputs == ("accuracy", "meets_threshold", "metrics")


def test_section_helpers_and_group_name_fallbacks(
    semantic_request: SemanticPlanningRequest,
) -> None:
    first_cell, *remaining_cells = semantic_request.facts.cells
    facts = replace(
        semantic_request.facts,
        cells=(replace(first_cell, source="Intro without a heading."), *remaining_cells),
    )
    request = replace(semantic_request, facts=facts)
    contexts = grouping_module.section_contexts_by_cell_id(request)
    tasks = semantic_request.baseline_plan.task_candidates[1:3]

    assert contexts["cell-0001"] == ("", "")
    assert grouping_module.task_section_contexts(("missing-cell",), contexts) == ()
    assert grouping_module._group_node_name(tasks, {}) == tasks[0].name

    numeric_contexts = {
        cell_id: ("heading", "## 123") for task in tasks for cell_id in task.source_cell_ids
    }
    keyword_contexts = {
        cell_id: ("heading", "## for") for task in tasks for cell_id in task.source_cell_ids
    }
    assert grouping_module._group_node_name(tasks, numeric_contexts) == tasks[0].name
    assert grouping_module._group_node_name(tasks, keyword_contexts) == tasks[0].name

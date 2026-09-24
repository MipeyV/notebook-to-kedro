"""Tests for deterministic semantic planning prompts."""

from dataclasses import replace

import pytest

from notebook_to_kedro.semantic import (
    SEMANTIC_PLANNING_PROMPT_VERSION,
    SemanticPlanningRequest,
    render_semantic_planning_prompt,
)


def test_prompt_is_deterministic_and_contains_the_canonical_request(
    semantic_request: SemanticPlanningRequest,
) -> None:
    prompt = render_semantic_planning_prompt(semantic_request)

    assert prompt == render_semantic_planning_prompt(semantic_request)
    assert semantic_request.prompt_version == SEMANTIC_PLANNING_PROMPT_VERSION
    assert semantic_request.to_json(indent=2) in prompt
    assert prompt.endswith("Do not create review, repair, warning, or diagnostic tasks.")
    assert "Include every baseline statement exactly once" in prompt
    assert "Diagnostics describe analysis limitations" in prompt
    assert "Valid default response JSON:" in prompt
    assert "Do not return Markdown fences" in prompt

    for task in semantic_request.baseline_plan.task_candidates:
        assert f'"node_name": "{task.name}"' in prompt
        for statement_id in task.statement_ids:
            assert prompt.count(f'"{statement_id}"') >= 2


def test_prompt_rejects_an_unsupported_version(
    semantic_request: SemanticPlanningRequest,
) -> None:
    request = replace(semantic_request, prompt_version="planning-unsupported")

    with pytest.raises(ValueError, match="unsupported semantic planning prompt version"):
        render_semantic_planning_prompt(request)

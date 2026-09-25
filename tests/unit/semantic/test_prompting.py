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
    assert prompt.endswith("Do not create review, repair, warning, or diagnostic groups.")
    assert "Include every baseline task ID exactly once" in prompt
    assert "Diagnostics describe analysis limitations" in prompt
    assert "Compact planning evidence JSON:" in prompt
    assert "Adjacent boundary review JSON:" in prompt
    assert "Evaluate every adjacent boundary in order as KEEP or MERGE" in prompt
    assert "Direct dataflow is evidence for MERGE" in prompt
    assert '"same_markdown_section": true' in prompt
    assert '"direct_dataflow": [' in prompt
    assert '"## Prepare features"' in prompt
    assert "Do not return Markdown fences" in prompt

    for task in semantic_request.baseline_plan.task_candidates:
        assert f'"current_node_name": "{task.name}"' in prompt
        for statement_id in task.statement_ids:
            assert prompt.count(f'"{statement_id}"') == 1


def test_prompt_rejects_an_unsupported_version(
    semantic_request: SemanticPlanningRequest,
) -> None:
    request = replace(semantic_request, prompt_version="planning-unsupported")

    with pytest.raises(ValueError, match="unsupported semantic planning prompt version"):
        render_semantic_planning_prompt(request)

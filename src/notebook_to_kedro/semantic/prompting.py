"""Deterministic prompt construction for semantic planning providers."""

import json
from itertools import pairwise

from notebook_to_kedro.semantic.contracts import SemanticPlanningRequest
from notebook_to_kedro.semantic.grouping import (
    SEMANTIC_GROUPING_SCHEMA_VERSION,
    section_contexts_by_cell_id,
    task_section_contexts,
)

SEMANTIC_PLANNING_PROMPT_VERSION = "planning-v3"
_DEFAULT_PIPELINE_ID = "notebook_pipeline"


def render_semantic_planning_prompt(request: SemanticPlanningRequest) -> str:
    """Render the supported semantic planning prompt without provider-specific syntax."""
    if request.prompt_version != SEMANTIC_PLANNING_PROMPT_VERSION:
        message = f"unsupported semantic planning prompt version: {request.prompt_version}"
        raise ValueError(message)

    planning_evidence = _planning_evidence(request)
    boundary_review = _boundary_review(request)
    return "\n".join(
        (
            "You structure an analyzed Python notebook into Kedro node suggestions.",
            "Return only one grouping JSON object matching the supplied response schema.",
            "",
            "Your task is boundary selection, not code repair:",
            "- Diagnostics describe analysis limitations; never turn them into tasks or fixes.",
            "- Do not rewrite code, explain fixes, or invent replacement identifiers.",
            "",
            "Rules:",
            "- Treat the compact planning evidence as immutable and complete.",
            "- Include every baseline task ID exactly once and preserve baseline order.",
            "- Every group must contain one or more adjacent baseline task IDs.",
            "- Never group tasks from different Markdown section identities.",
            "- A baseline task with multiple statement IDs is already cohesive; keep it alone.",
            "- Do not return cell IDs, statements, interfaces, names, code, or review prose.",
            "- Do not return Markdown fences or prose outside the JSON object.",
            "",
            "Compact planning evidence JSON:",
            json.dumps(planning_evidence, indent=2, ensure_ascii=True, sort_keys=True),
            "",
            "Adjacent boundary review JSON:",
            json.dumps(boundary_review, indent=2, ensure_ascii=True, sort_keys=True),
            "",
            "Boundary decision procedure:",
            "- Evaluate every adjacent boundary in order as KEEP or MERGE.",
            "- KEEP when Markdown sections differ; this is a hard boundary.",
            (
                "- Within one section, KEEP only distinct lifecycle transitions such as "
                "prepare to split, train to predict, or predict to evaluate."
            ),
            (
                "- Otherwise MERGE same-section fragments when names share a purpose or one "
                "fragment directly feeds the next."
            ),
            "- Direct dataflow is evidence for MERGE, not a reason to KEEP two fragments.",
            "- Loading plus extraction is one load operation; construction plus fit is training.",
            "- Cleaning plus feature/target selection is one preparation operation.",
            "- Metric calculation plus threshold/summary construction is one evaluation.",
            "- A chain of MERGE decisions becomes one group of baseline task IDs.",
            "- Preserve singleton groups only when the surrounding boundaries should be KEEP.",
            "",
            "Return one grouping JSON object now after applying the boundary decisions.",
            (
                f"Use schema_version {SEMANTIC_GROUPING_SCHEMA_VERSION!r} and request_id "
                f"{request.request_id!r} exactly."
            ),
            "Do not create review, repair, warning, or diagnostic groups.",
        )
    )


def _planning_evidence(request: SemanticPlanningRequest) -> dict[str, object]:
    sections_by_cell = section_contexts_by_cell_id(request)
    return {
        "pipeline_id": _DEFAULT_PIPELINE_ID,
        "request_id": request.request_id,
        "schema_version": request.schema_version,
        "tasks": [
            {
                "current_node_name": task.name,
                "inputs": list(task.inputs),
                "outputs": list(task.outputs),
                "parameter_names": list(task.parameters),
                "section_headings": [
                    context[1]
                    for context in task_section_contexts(task.source_cell_ids, sections_by_cell)
                ],
                "source": task.source,
                "source_cell_ids": list(task.source_cell_ids),
                "statement_ids": list(task.statement_ids),
                "task_id": task.id,
            }
            for task in request.baseline_plan.task_candidates
        ],
    }


def _boundary_review(request: SemanticPlanningRequest) -> list[dict[str, object]]:
    sections_by_cell = section_contexts_by_cell_id(request)
    tasks = request.baseline_plan.task_candidates
    review: list[dict[str, object]] = []
    for left, right in pairwise(tasks):
        left_sections = task_section_contexts(left.source_cell_ids, sections_by_cell)
        right_sections = task_section_contexts(right.source_cell_ids, sections_by_cell)
        right_inputs = set(right.inputs)
        review.append(
            {
                "direct_dataflow": [name for name in left.outputs if name in right_inputs],
                "left_task_id": left.id,
                "right_task_id": right.id,
                "same_markdown_section": bool(left_sections) and left_sections == right_sections,
            }
        )
    return review

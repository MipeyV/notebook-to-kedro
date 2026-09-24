"""Deterministic prompt construction for semantic planning providers."""

from notebook_to_kedro.semantic.contracts import (
    SemanticPlanningRequest,
    SemanticPlanningResponse,
    SemanticTaskSuggestion,
)

SEMANTIC_PLANNING_PROMPT_VERSION = "planning-v2"
_DEFAULT_PIPELINE_ID = "notebook_pipeline"


def render_semantic_planning_prompt(request: SemanticPlanningRequest) -> str:
    """Render the supported semantic planning prompt without provider-specific syntax."""
    if request.prompt_version != SEMANTIC_PLANNING_PROMPT_VERSION:
        message = f"unsupported semantic planning prompt version: {request.prompt_version}"
        raise ValueError(message)

    default_response = _baseline_response(request)
    return "\n".join(
        (
            "You structure an analyzed Python notebook into Kedro node suggestions.",
            "Return only one JSON object matching the supplied response schema.",
            "",
            "Your task is boundary selection, not code repair:",
            "- Diagnostics describe analysis limitations; never turn them into tasks or fixes.",
            "- Do not rewrite code, explain fixes, or invent replacement identifiers.",
            "- The valid default response below mirrors the deterministic baseline.",
            "- Return the default unchanged unless adjacent baseline tasks clearly form one node.",
            "",
            "Rules:",
            "- Treat notebook_facts and baseline_plan as immutable evidence.",
            "- Copy source_cell_ids and statement_ids exactly from baseline task candidates.",
            "- Include every baseline statement exactly once; never split a baseline task.",
            "- Only merge baseline tasks that are adjacent in baseline_plan.task_candidates.",
            "- Use only existing input, output, and parameter names; never put prose in them.",
            f"- Always use pipeline_id {_DEFAULT_PIPELINE_ID!r}.",
            "- Use public ASCII Python identifiers for node_name and pipeline_id.",
            "- Put uncertainty and review requirements in review_notes.",
            "- Do not return Markdown fences, prose outside JSON, or generated node code.",
            "",
            "Request JSON:",
            request.to_json(indent=2),
            "",
            "Valid default response JSON:",
            default_response.to_json(indent=2),
            "",
            "Return one response JSON object now. Prefer the valid default response.",
            "Do not create review, repair, warning, or diagnostic tasks.",
        )
    )


def _baseline_response(request: SemanticPlanningRequest) -> SemanticPlanningResponse:
    return SemanticPlanningResponse(
        schema_version=request.schema_version,
        request_id=request.request_id,
        tasks=tuple(
            SemanticTaskSuggestion(
                source_cell_ids=task.source_cell_ids,
                statement_ids=task.statement_ids,
                node_name=task.name,
                inputs=task.inputs,
                outputs=task.outputs,
                parameter_names=task.parameters,
                pipeline_id=_DEFAULT_PIPELINE_ID,
            )
            for task in request.baseline_plan.task_candidates
        ),
    )

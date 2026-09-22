"""Deterministic prompt construction for semantic planning providers."""

from notebook_to_kedro.semantic.contracts import SemanticPlanningRequest

SEMANTIC_PLANNING_PROMPT_VERSION = "planning-v1"


def render_semantic_planning_prompt(request: SemanticPlanningRequest) -> str:
    """Render the supported semantic planning prompt without provider-specific syntax."""
    if request.prompt_version != SEMANTIC_PLANNING_PROMPT_VERSION:
        message = f"unsupported semantic planning prompt version: {request.prompt_version}"
        raise ValueError(message)

    return "\n".join(
        (
            "You structure an analyzed Python notebook into Kedro node suggestions.",
            "Return only one JSON object matching the supplied response schema.",
            "",
            "Rules:",
            "- Treat notebook_facts and baseline_plan as immutable evidence.",
            "- Include every baseline statement exactly once across the suggested tasks.",
            "- Never invent cell IDs, statement IDs, inputs, outputs, or parameters.",
            "- Use public ASCII Python identifiers for node_name and pipeline_id.",
            "- Put uncertainty and review requirements in review_notes.",
            "- Do not return Markdown fences, prose outside JSON, or generated node code.",
            "",
            "Request JSON:",
            request.to_json(indent=2),
        )
    )

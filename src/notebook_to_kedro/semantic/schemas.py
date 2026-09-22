"""JSON schemas exposed to structured-output semantic planning providers."""

from notebook_to_kedro.semantic.contracts import SEMANTIC_PLANNING_SCHEMA_VERSION

_STRING_ARRAY_SCHEMA: dict[str, object] = {
    "type": "array",
    "items": {"type": "string", "minLength": 1},
    "uniqueItems": True,
}
_NON_EMPTY_STRING_ARRAY_SCHEMA: dict[str, object] = {
    **_STRING_ARRAY_SCHEMA,
    "minItems": 1,
}
_IDENTIFIER_SCHEMA: dict[str, object] = {
    "type": "string",
    "pattern": "^[A-Za-z][A-Za-z0-9_]*$",
}

SEMANTIC_PLANNING_RESPONSE_JSON_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "SemanticPlanningResponse",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "request_id", "tasks", "review_notes"],
    "properties": {
        "schema_version": {
            "type": "string",
            "const": SEMANTIC_PLANNING_SCHEMA_VERSION,
        },
        "request_id": {"type": "string", "minLength": 1},
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "source_cell_ids",
                    "statement_ids",
                    "node_name",
                    "inputs",
                    "outputs",
                    "parameter_names",
                    "pipeline_id",
                    "review_notes",
                ],
                "properties": {
                    "source_cell_ids": _NON_EMPTY_STRING_ARRAY_SCHEMA,
                    "statement_ids": _NON_EMPTY_STRING_ARRAY_SCHEMA,
                    "node_name": _IDENTIFIER_SCHEMA,
                    "inputs": _STRING_ARRAY_SCHEMA,
                    "outputs": _STRING_ARRAY_SCHEMA,
                    "parameter_names": _STRING_ARRAY_SCHEMA,
                    "pipeline_id": _IDENTIFIER_SCHEMA,
                    "review_notes": _STRING_ARRAY_SCHEMA,
                },
            },
        },
        "review_notes": _STRING_ARRAY_SCHEMA,
    },
}

"""Structured-output schema for the node code response, version 1.0."""

NODE_CODE_RESPONSE_JSON_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "NodeCodeResponse",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "request_id",
        "task_id",
        "function_code",
        "imports",
        "review_notes",
    ],
    "properties": {
        "schema_version": {"type": "string", "const": "1.0"},
        "request_id": {"type": "string", "minLength": 1, "pattern": r"\S"},
        "task_id": {"type": "string", "minLength": 1, "pattern": r"\S"},
        "function_code": {"type": "string", "minLength": 1, "pattern": r"\S"},
        "imports": {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1, "pattern": r"\S"},
        },
        "review_notes": {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1, "pattern": r"\S"},
        },
    },
}

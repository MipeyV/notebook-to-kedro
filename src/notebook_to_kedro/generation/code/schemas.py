"""Structured-output schemas for full-code and body-only node responses."""

from notebook_to_kedro.generation.code.contracts import NODE_BODY_SCHEMA_VERSION

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

NODE_BODY_RESPONSE_JSON_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "NodeBodyResponse",
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "request_id", "task_id", "body_code", "review_notes"],
    "properties": {
        "schema_version": {"type": "string", "const": NODE_BODY_SCHEMA_VERSION},
        "request_id": {"type": "string", "minLength": 1, "pattern": r"\S"},
        "task_id": {"type": "string", "minLength": 1, "pattern": r"\S"},
        "body_code": {"type": "string", "minLength": 1, "pattern": r"\S"},
        "review_notes": {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1, "pattern": r"\S"},
        },
    },
}

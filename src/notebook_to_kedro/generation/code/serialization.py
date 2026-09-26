"""Strict JSON primitives for the node code contract."""

import json
from typing import Any


def encode_object(data: dict[str, object], *, indent: int | None) -> str:
    """Encode with deterministic ordering and ASCII escapes."""
    return json.dumps(data, indent=indent, ensure_ascii=True, sort_keys=True)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def decode_object(
    payload: str, strings: tuple[str, ...], arrays: tuple[str, ...]
) -> dict[str, Any]:
    """Reject missing, extra, duplicate and incorrectly typed fields."""
    data = json.loads(payload, object_pairs_hook=_unique_object)
    if not isinstance(data, dict) or set(data) != {*strings, *arrays}:
        raise ValueError("node code fields must match the versioned contract exactly")
    for field in strings:
        if not isinstance(data[field], str):
            raise ValueError(f"{field} must be a string")
    for field in arrays:
        value = data[field]
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"{field} must be an array of strings")
        data[field] = tuple(value)
    return data

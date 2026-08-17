"""Unit tests for deterministic notebook facts serialization."""

import copy
import json
from collections.abc import Callable
from typing import cast

import pytest

from notebook_to_kedro.ir import (
    Diagnostic,
    NotebookFacts,
    NotebookMetadata,
    Severity,
    notebook_facts_from_dict,
    notebook_facts_from_json,
    notebook_facts_to_dict,
    notebook_facts_to_json,
)


def test_notebook_facts_round_trip_through_dict(notebook_facts: NotebookFacts) -> None:
    """The canonical dictionary reconstructs the original immutable document."""
    payload = notebook_facts.to_dict()

    assert notebook_facts_from_dict(payload) == notebook_facts
    assert NotebookFacts.from_dict(payload) == notebook_facts


def test_notebook_facts_round_trip_through_json(notebook_facts: NotebookFacts) -> None:
    """Pretty and compact JSON preserve all canonical facts."""
    pretty = notebook_facts.to_json()
    compact = notebook_facts_to_json(notebook_facts, indent=None)

    assert NotebookFacts.from_json(pretty) == notebook_facts
    assert notebook_facts_from_json(compact) == notebook_facts
    assert "\n" in pretty
    assert "\n" not in compact
    assert compact.startswith('{"analyzer_version"')


def test_serialization_is_repeatable_and_unicode_safe(notebook_facts: NotebookFacts) -> None:
    """Identical documents always produce identical UTF-8-friendly JSON text."""
    first = notebook_facts_to_json(notebook_facts)
    second = notebook_facts_to_json(notebook_facts)

    assert first == second
    assert "Method call may mutate" in first
    assert "\\u" not in first


def test_top_level_function_and_method_return_the_same_mapping(
    notebook_facts: NotebookFacts,
) -> None:
    """Convenience methods do not define a second serialization behavior."""
    assert notebook_facts_to_dict(notebook_facts) == notebook_facts.to_dict()


def test_json_root_must_be_an_object() -> None:
    """Decoded JSON arrays cannot masquerade as a facts document."""
    with pytest.raises(TypeError, match="root must be an object"):
        notebook_facts_from_json("[]")


def test_required_field_must_be_present(notebook_facts: NotebookFacts) -> None:
    """Missing contract fields produce an actionable error."""
    payload = notebook_facts.to_dict()
    del payload["schema_version"]

    with pytest.raises(ValueError, match="missing required field: schema_version"):
        notebook_facts_from_dict(payload)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.update(schema_version=1), "must be a string"),
        (lambda payload: payload.update(cells="invalid"), "must be an array"),
        (
            lambda payload: cast("dict[object, object]", payload["notebook"]).update({1: "x"}),
            "keys must be strings",
        ),
        (
            lambda payload: cast("dict[str, object]", payload["notebook"]).update(nbformat=True),
            "must be an integer",
        ),
        (
            lambda payload: cast("dict[str, object]", payload["notebook"]).update(kernel_name=3),
            "must be a string",
        ),
        (
            lambda payload: cast(
                "dict[str, object]", cast("list[object]", payload["cells"])[0]
            ).update(execution_count="one"),
            "must be an integer",
        ),
        (
            lambda payload: cast(
                "dict[str, object]",
                cast(
                    "list[object]",
                    cast("dict[str, object]", cast("list[object]", payload["cells"])[0])[
                        "statements"
                    ],
                )[0],
            ).update(conditional=1),
            "must be a boolean",
        ),
        (
            lambda payload: cast(
                "dict[str, object]",
                cast(
                    "list[object]",
                    cast("dict[str, object]", cast("list[object]", payload["cells"])[0])["calls"],
                )[0],
            ).update(literal_arguments=[{}]),
            "must be a JSON primitive",
        ),
        (
            lambda payload: cast(
                "dict[str, object]",
                cast(
                    "list[object]",
                    cast("dict[str, object]", cast("list[object]", payload["cells"])[0])[
                        "statements"
                    ],
                )[0],
            ).update(location=None),
            "must not be null",
        ),
    ],
)
def test_deserialization_rejects_wrong_field_types(
    notebook_facts: NotebookFacts,
    mutation: Callable[[dict[str, object]], None],
    message: str,
) -> None:
    """Type errors are reported at the canonical decoding boundary."""
    payload = copy.deepcopy(notebook_facts.to_dict())
    mutation(payload)

    with pytest.raises(TypeError, match=message):
        notebook_facts_from_dict(payload)


def test_deserialization_rejects_non_string_array_items(
    notebook_facts: NotebookFacts,
) -> None:
    """String summary arrays validate every member."""
    payload = copy.deepcopy(notebook_facts.to_dict())
    first_cell = cast("dict[str, object]", cast("list[object]", payload["cells"])[0])
    first_cell["reads"] = [1]

    with pytest.raises(TypeError, match="item must be a string"):
        notebook_facts_from_dict(payload)


def test_deserialization_rejects_notebook_facts_subclasses(
    notebook_facts: NotebookFacts,
) -> None:
    """Factories cannot imply support for reconstructing unknown subclasses."""

    class SpecializedFacts(NotebookFacts):
        pass

    with pytest.raises(TypeError, match="does not support subclasses"):
        SpecializedFacts.from_dict(notebook_facts.to_dict())


def test_standard_json_decoder_errors_remain_visible() -> None:
    """Malformed JSON retains the standard decoder exception type."""
    with pytest.raises(json.JSONDecodeError):
        notebook_facts_from_json("{")


def test_optional_source_location_serializes_as_null() -> None:
    """Notebook-level diagnostics may omit a cell source location."""
    facts = NotebookFacts(
        schema_version="1.0",
        analyzer_version="0.1.0",
        notebook=NotebookMetadata(
            path="notebooks/empty.ipynb",
            nbformat=4,
            nbformat_minor=5,
            language="python",
            kernel_name=None,
            cell_count=0,
            content_sha256="a" * 64,
        ),
        cells=(),
        diagnostics=(
            Diagnostic(
                id="diagnostic-0000",
                code="NB001",
                severity=Severity.ERROR,
                message="Notebook validation failed.",
                blocking=True,
            ),
        ),
    )

    diagnostics = cast("list[dict[str, object]]", facts.to_dict()["diagnostics"])
    assert diagnostics[0]["location"] is None

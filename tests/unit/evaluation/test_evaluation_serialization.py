"""Unit tests for planning evaluation corpus serialization."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from notebook_to_kedro.evaluation import (
    load_planning_case,
    load_planning_corpus,
    planning_case_from_dict,
    planning_case_from_json,
    planning_case_to_dict,
    planning_case_to_json,
)

CORPUS = Path(__file__).parents[2] / "fixtures" / "evaluation" / "planning" / "v1"
PayloadMutation = Callable[[dict[str, object]], dict[str, object]]


def _payload() -> dict[str, object]:
    case = load_planning_case(CORPUS / "simple_training.json")
    return planning_case_to_dict(case)


def _replace_first_task(payload: dict[str, object], **changes: object) -> dict[str, object]:
    tasks = payload["tasks"]
    assert isinstance(tasks, list)
    first_task = tasks[0]
    assert isinstance(first_task, dict)
    return {**payload, "tasks": [{**first_task, **changes}]}


def test_planning_case_round_trips_through_dict_and_json() -> None:
    case = load_planning_case(CORPUS / "simple_training.json")

    assert planning_case_from_dict(planning_case_to_dict(case)) == case
    assert planning_case_from_json(planning_case_to_json(case)) == case
    assert planning_case_to_json(case, indent=None).endswith("\n")


def test_load_planning_corpus_uses_deterministic_filename_order() -> None:
    cases = load_planning_corpus(CORPUS)

    assert tuple(case.case_id for case in cases) == (
        "file-backed-training",
        "pandas-preprocessing-training",
        "scaled-training",
        "simple-training",
    )


INVALID_PAYLOADS: list[tuple[PayloadMutation, str]] = [
    (lambda payload: {**payload, "unexpected": True}, "invalid planning case fields"),
    (lambda payload: {**payload, "tasks": "invalid"}, "tasks must be an array"),
    (lambda payload: {**payload, "review_status": "pending"}, "must be 'approved'"),
    (lambda payload: {**payload, "case_id": 42}, "case_id must be a string"),
    (
        lambda payload: {**payload, "expected_parameter_names": "invalid"},
        "must be an array of strings",
    ),
    (
        lambda payload: {**payload, "expected_parameter_names": [42]},
        "must be an array of strings",
    ),
    (lambda payload: {**payload, "tasks": [42]}, "expected task must be an object"),
    (
        lambda payload: _replace_first_task(payload, unexpected=True),
        "invalid expected task fields",
    ),
    (
        lambda payload: _replace_first_task(payload, raw_source=42),
        "raw_source must be a string",
    ),
]


@pytest.mark.parametrize(("mutate", "message"), INVALID_PAYLOADS)
def test_planning_case_from_dict_rejects_invalid_payloads(
    mutate: PayloadMutation, message: str
) -> None:
    invalid = mutate(_payload())

    with pytest.raises(ValueError, match=message):
        planning_case_from_dict(invalid)


def test_planning_case_from_dict_rejects_non_string_object_keys() -> None:
    with pytest.raises(ValueError, match="object with string keys"):
        planning_case_from_dict({1: "invalid"})


def test_planning_case_from_json_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="invalid planning case JSON"):
        planning_case_from_json("{")


def test_load_planning_case_reports_read_errors(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot read planning case"):
        load_planning_case(tmp_path / "missing.json")


def test_load_planning_corpus_rejects_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="contains no JSON cases"):
        load_planning_corpus(tmp_path)


def test_load_planning_corpus_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = json.dumps(_payload())
    (tmp_path / "first.json").write_text(payload, encoding="utf-8")
    (tmp_path / "second.json").write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_planning_corpus(tmp_path)

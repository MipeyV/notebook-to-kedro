"""Independent node-code corpus contracts, serialization and static metrics."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from notebook_to_kedro.evaluation import (
    NODE_CODE_CASE_SCHEMA_VERSION,
    NodeCodeCase,
    NodeCodeCaseEvaluation,
    NodeCodeCorpusEvaluation,
    evaluate_node_code_case,
    evaluate_node_code_corpus,
    load_node_code_case,
    load_node_code_corpus,
    node_code_case_from_dict,
    node_code_case_from_json,
    node_code_case_to_dict,
    node_code_case_to_json,
    verify_node_code_case_source,
)

ROOT = Path(__file__).parents[3]
CORPUS = ROOT / "tests/fixtures/evaluation/node_code/v1"


@pytest.fixture
def case() -> NodeCodeCase:
    return load_node_code_case(CORPUS / "custom_ratio.json")


def test_case_round_trips_and_corpus_order_is_deterministic(case: NodeCodeCase) -> None:
    assert NODE_CODE_CASE_SCHEMA_VERSION == "1.0"
    assert node_code_case_from_dict(node_code_case_to_dict(case)) == case
    assert node_code_case_from_json(node_code_case_to_json(case)) == case
    assert node_code_case_to_json(case, indent=None).endswith("\n")
    assert tuple(item.case_id for item in load_node_code_corpus(CORPUS)) == (
        "custom-ratio",
        "evaluate-regression",
        "fill-missing",
        "split-holdout",
    )


def test_reviewed_corpus_measures_dimensions_without_false_rejections() -> None:
    result = evaluate_node_code_corpus(load_node_code_corpus(CORPUS))
    assert result.reference_count == result.reference_accepted_count == 4
    assert result.false_rejection_count == result.missed_invalid_count == 0
    assert result.invalid_example_count == result.detected_invalid_count == 9
    assert result.exact_match
    assert all(case.exact_match for case in result.cases)
    assert all(case.reference.expected_valid for case in result.cases)
    assert all(case.reference.compilation_valid for case in result.cases)
    assert all(case.reference.static_valid for case in result.cases)
    assert all(case.reference.reference_ast_match for case in result.cases)
    invalid = {item.candidate_id: item for case in result.cases for item in case.invalid_examples}
    assert not invalid["malformed-function"].compilation_valid
    assert not invalid["malformed-function"].reference_ast_match
    assert invalid["missing-required-import"].compilation_valid
    assert invalid["missing-required-import"].reference_ast_match
    assert all(not item.expected_valid and not item.static_valid for item in invalid.values())


def test_missed_invalid_and_false_rejection_metrics_are_explicit(case: NodeCodeCase) -> None:
    accepted_invalid = replace(case.invalid_examples[0], response=case.reference_response)
    missed_case = replace(case, invalid_examples=(accepted_invalid,))
    missed = evaluate_node_code_case(missed_case)
    assert not missed.exact_match
    assert not missed.invalid_examples[0].expected_outcome_match
    assert missed.invalid_examples[0].diagnostic_message is None

    rejected_reference = replace(case, reference_response=case.invalid_examples[0].response)
    false_rejection = evaluate_node_code_corpus((rejected_reference,))
    assert false_rejection.reference_count == 1
    assert false_rejection.reference_accepted_count == 0
    assert false_rejection.false_rejection_count == 1
    assert not false_rejection.exact_match

    wrong_diagnostic = replace(
        case.invalid_examples[0], expected_error_contains="different diagnostic"
    )
    mismatch = evaluate_node_code_case(replace(case, invalid_examples=(wrong_diagnostic,)))
    assert not mismatch.invalid_examples[0].expected_outcome_match
    assert mismatch.invalid_examples[0].diagnostic_message is not None


def test_empty_evaluation_has_no_exact_match() -> None:
    assert not NodeCodeCorpusEvaluation(()).exact_match


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"schema_version": "2.0"}, "unsupported node code case schema"),
        ({"case_id": ""}, "case id must not be empty"),
        ({"notebook_path": " "}, "notebook path must not be empty"),
        ({"source_sha256": "short"}, "64-character hexadecimal"),
        ({"source_sha256": "g" * 64}, "64-character hexadecimal"),
        ({"review_status": "pending"}, "explicitly approved"),
        ({"invalid_examples": ()}, "at least one invalid example"),
    ],
)
def test_case_rejects_invalid_fields(
    case: NodeCodeCase, mutation: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(case, **mutation)  # type: ignore[arg-type]


def test_case_rejects_duplicate_examples_and_response_identity(case: NodeCodeCase) -> None:
    duplicate = replace(case.invalid_examples[1], id=case.invalid_examples[0].id)
    with pytest.raises(ValueError, match="candidate IDs must be unique"):
        replace(case, invalid_examples=(case.invalid_examples[0], duplicate))
    with pytest.raises(ValueError, match="candidate IDs must be unique"):
        replace(case, invalid_examples=(replace(case.invalid_examples[0], id="reference"),))
    wrong = replace(case.reference_response, request_id="other")
    with pytest.raises(ValueError, match="responses must match"):
        replace(case, reference_response=wrong)
    invalid_wrong = replace(
        case.invalid_examples[0],
        response=replace(case.invalid_examples[0].response, task_id="other"),
    )
    with pytest.raises(ValueError, match="responses must match"):
        replace(case, invalid_examples=(invalid_wrong,))


def test_invalid_example_rejects_empty_review_fields(case: NodeCodeCase) -> None:
    with pytest.raises(ValueError, match="example id must not be empty"):
        replace(case.invalid_examples[0], id=" ")
    with pytest.raises(ValueError, match="error fragment must not be empty"):
        replace(case.invalid_examples[0], expected_error_contains="")


def test_evaluator_rejects_empty_or_duplicate_case_ids(case: NodeCodeCase) -> None:
    with pytest.raises(ValueError, match="at least one case"):
        evaluate_node_code_corpus(())
    with pytest.raises(ValueError, match="case IDs must be unique"):
        evaluate_node_code_corpus((case, case))


def test_case_evaluation_exact_match_requires_every_candidate(case: NodeCodeCase) -> None:
    result = evaluate_node_code_case(case)
    bad_candidate = replace(result.invalid_examples[0], expected_outcome_match=False)
    assert not NodeCodeCaseEvaluation(
        case_id=result.case_id,
        reference=result.reference,
        invalid_examples=(bad_candidate,),
    ).exact_match
    bad_reference = replace(result.reference, expected_outcome_match=False)
    assert not NodeCodeCaseEvaluation(
        case_id=result.case_id,
        reference=bad_reference,
        invalid_examples=result.invalid_examples,
    ).exact_match


def _payload(case: NodeCodeCase) -> dict[str, object]:
    return node_code_case_to_dict(case)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: {**data, "extra": True}, "invalid node code case fields"),
        (lambda data: {**data, "review_status": "pending"}, "must be 'approved'"),
        (lambda data: {**data, "case_id": 1}, "case_id must be a string"),
        (lambda data: {**data, "invalid_examples": "bad"}, "must be an array"),
        (lambda data: {**data, "request": []}, "request must be an object"),
        (lambda data: {**data, "reference_response": []}, "response must be an object"),
        (lambda data: {**data, "invalid_examples": [1]}, "example must be an object"),
        (
            lambda data: {
                **data,
                "invalid_examples": [{**data["invalid_examples"][0], "extra": True}],
            },
            "invalid invalid node code example fields",
        ),
        (
            lambda data: {
                **data,
                "invalid_examples": [{**data["invalid_examples"][0], "expected_error_contains": 1}],
            },
            "expected_error_contains must be a string",
        ),
    ],
)
def test_case_decoder_rejects_invalid_payloads(
    case: NodeCodeCase, mutate: object, message: str
) -> None:
    invalid = mutate(_payload(case))  # type: ignore[operator]
    with pytest.raises(ValueError, match=message):
        node_code_case_from_dict(invalid)


def test_case_decoder_rejects_non_string_keys_and_invalid_json() -> None:
    with pytest.raises(ValueError, match="object with string keys"):
        node_code_case_from_dict({1: "invalid"})
    with pytest.raises(ValueError, match="invalid node code case JSON"):
        node_code_case_from_json("{")


def test_case_loader_reports_filesystem_and_corpus_errors(
    case: NodeCodeCase, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="cannot read node code case"):
        load_node_code_case(tmp_path / "missing.json")
    with pytest.raises(ValueError, match="contains no JSON cases"):
        load_node_code_corpus(tmp_path)
    payload = node_code_case_to_json(case)
    (tmp_path / "a.json").write_text(payload, encoding="utf-8")
    (tmp_path / "b.json").write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_node_code_corpus(tmp_path)


def test_source_verification_reports_hash_source_and_notebook_errors(
    case: NodeCodeCase, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="cannot read node code case notebook"):
        verify_node_code_case_source(
            replace(case, notebook_path="missing.ipynb"), project_root=tmp_path
        )

    source = tmp_path / "source.ipynb"
    source.write_text('{"cells": []}', encoding="utf-8")
    relative = source.relative_to(tmp_path).as_posix()
    with pytest.raises(ValueError, match="source hash does not match"):
        verify_node_code_case_source(
            replace(case, notebook_path=relative, source_sha256="0" * 64), project_root=tmp_path
        )

    def reviewed(content: bytes) -> NodeCodeCase:
        source.write_bytes(content)
        return replace(
            case,
            notebook_path=relative,
            source_sha256=hashlib.sha256(content).hexdigest(),
        )

    with pytest.raises(ValueError, match="invalid node code case notebook"):
        verify_node_code_case_source(reviewed(b"{"), project_root=tmp_path)
    with pytest.raises(ValueError, match="invalid node code case notebook"):
        verify_node_code_case_source(reviewed(b"{}"), project_root=tmp_path)
    with pytest.raises(ValueError, match="invalid node code case notebook"):
        verify_node_code_case_source(reviewed(b'{"cells": null}'), project_root=tmp_path)
    malformed_source = json.dumps(
        {"cells": [{"id": "bad-cell", "cell_type": "code", "source": [1]}]}
    ).encode()
    with pytest.raises(ValueError, match="invalid node code case notebook"):
        verify_node_code_case_source(reviewed(malformed_source), project_root=tmp_path)
    with pytest.raises(ValueError, match="source and cell provenance"):
        verify_node_code_case_source(reviewed(b'{"cells": []}'), project_root=tmp_path)

    matching_source_wrong_id = json.dumps(
        {
            "cells": [
                {
                    "id": "different-cell",
                    "cell_type": "code",
                    "source": [case.request.raw_source],
                }
            ]
        }
    ).encode()
    with pytest.raises(ValueError, match="source and cell provenance"):
        verify_node_code_case_source(reviewed(matching_source_wrong_id), project_root=tmp_path)

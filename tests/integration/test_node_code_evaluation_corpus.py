"""Integrity and reviewed outcomes for the independent node-code corpus."""

from pathlib import Path

import pytest

from notebook_to_kedro.evaluation import (
    evaluate_node_code_corpus,
    load_node_code_corpus,
    verify_node_code_case_source,
)

ROOT = Path(__file__).parents[2]
CORPUS = ROOT / "tests/fixtures/evaluation/node_code"


@pytest.mark.parametrize(
    ("version", "references", "invalid_examples"), [("v1", 4, 9), ("v2", 8, 17)]
)
def test_independent_node_code_corpus_is_traceable_and_matches_review(
    version: str, references: int, invalid_examples: int
) -> None:
    cases = load_node_code_corpus(CORPUS / version)
    for case in cases:
        verify_node_code_case_source(case, project_root=ROOT)

    result = evaluate_node_code_corpus(cases)
    assert result.reference_count == result.reference_accepted_count == references
    assert result.false_rejection_count == result.missed_invalid_count == 0
    assert result.invalid_example_count == result.detected_invalid_count == invalid_examples
    assert result.exact_match


def test_expanded_node_corpus_preserves_the_frozen_baseline() -> None:
    baseline = load_node_code_corpus(CORPUS / "v1")
    expanded = {case.case_id: case for case in load_node_code_corpus(CORPUS / "v2")}

    assert all(expanded[case.case_id] == case for case in baseline)
    assert set(expanded) - {case.case_id for case in baseline} == {
        "aggregate-orders",
        "join-customers",
        "encode-categories",
        "date-features",
    }

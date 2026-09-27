"""Integrity and reviewed outcomes for the independent node-code corpus."""

from pathlib import Path

from notebook_to_kedro.evaluation import (
    evaluate_node_code_corpus,
    load_node_code_corpus,
    verify_node_code_case_source,
)

ROOT = Path(__file__).parents[2]
CORPUS = ROOT / "tests/fixtures/evaluation/node_code/v1"


def test_independent_node_code_corpus_is_traceable_and_matches_review() -> None:
    cases = load_node_code_corpus(CORPUS)
    for case in cases:
        verify_node_code_case_source(case, project_root=ROOT)

    result = evaluate_node_code_corpus(cases)
    assert result.reference_count == result.reference_accepted_count == 4
    assert result.false_rejection_count == result.missed_invalid_count == 0
    assert result.invalid_example_count == result.detected_invalid_count == 9
    assert result.exact_match

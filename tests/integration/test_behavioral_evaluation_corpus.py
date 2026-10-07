"""Cross-contract integrity for reviewed behavioral evidence."""

from pathlib import Path

import pytest

from notebook_to_kedro.evaluation import (
    load_behavioral_corpus,
    load_node_code_corpus,
    validate_behavioral_corpus,
)

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    ("version", "scenario_count", "exception_count", "output_count"),
    [("v1", 5, 1, 7), ("v2", 17, 5, 15), ("v3", 12, 4, 18)],
)
def test_behavioral_corpus_matches_independent_node_code_interfaces(
    version: str, scenario_count: int, exception_count: int, output_count: int
) -> None:
    behaviors = load_behavioral_corpus(ROOT / "tests/fixtures/evaluation/behavioral" / version)
    nodes = load_node_code_corpus(ROOT / "tests/fixtures/evaluation/node_code" / version)
    validate_behavioral_corpus(behaviors, nodes)

    assert len(behaviors) == scenario_count
    assert sum(case.expected_exception is not None for case in behaviors) == exception_count
    assert sum(len(case.expected_outputs) for case in behaviors) == output_count


def test_expanded_behavioral_corpus_preserves_baseline_and_exercises_each_new_task() -> None:
    baseline = load_behavioral_corpus(ROOT / "tests/fixtures/evaluation/behavioral/v1")
    expanded = load_behavioral_corpus(ROOT / "tests/fixtures/evaluation/behavioral/v2")
    by_id = {case.case_id: case for case in expanded}

    assert all(by_id[case.case_id] == case for case in baseline)
    for node_id in ("aggregate-orders", "join-customers", "encode-categories", "date-features"):
        scenarios = tuple(case for case in expanded if case.node_code_case_id == node_id)
        assert len(scenarios) == 3
        assert sum(case.expected_exception is not None for case in scenarios) == 1

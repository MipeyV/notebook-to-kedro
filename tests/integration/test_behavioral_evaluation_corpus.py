"""Cross-contract integrity for reviewed behavioral evidence."""

from pathlib import Path

from notebook_to_kedro.evaluation import (
    load_behavioral_corpus,
    load_node_code_corpus,
    validate_behavioral_corpus,
)

ROOT = Path(__file__).parents[2]


def test_behavioral_corpus_matches_independent_node_code_interfaces() -> None:
    behaviors = load_behavioral_corpus(ROOT / "tests/fixtures/evaluation/behavioral/v1")
    nodes = load_node_code_corpus(ROOT / "tests/fixtures/evaluation/node_code/v1")
    validate_behavioral_corpus(behaviors, nodes)

    assert len(behaviors) == 5
    assert sum(case.expected_exception is not None for case in behaviors) == 1
    assert sum(len(case.expected_outputs) for case in behaviors) == 7

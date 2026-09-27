from pathlib import Path

import pytest

from notebook_to_kedro.evaluation import (
    execute_behavioral_reference,
    load_behavioral_corpus,
    load_node_code_corpus,
)


@pytest.mark.integration
def test_all_reviewed_behavioral_references_execute_in_isolated_workers() -> None:
    behaviors = load_behavioral_corpus(Path("tests/fixtures/evaluation/behavioral/v1"))
    nodes = {
        case.case_id: case
        for case in load_node_code_corpus(Path("tests/fixtures/evaluation/node_code/v1"))
    }

    results = tuple(
        execute_behavioral_reference(case, nodes[case.node_code_case_id]) for case in behaviors
    )

    assert tuple(result.case_id for result in results) == tuple(case.case_id for case in behaviors)
    assert tuple(result.status for result in results) == (
        "success",
        "exception",
        "success",
        "success",
        "success",
    )
    exception = results[1].exception
    assert exception is not None
    assert exception.type_name == "KeyError"
    assert "revenue" in exception.message

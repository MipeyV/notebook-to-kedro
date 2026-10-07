"""Independent v3 source integrity, assembly and scenario sensitivity."""

import ast
from pathlib import Path
from typing import TYPE_CHECKING, cast

import nbformat
import pytest

from notebook_to_kedro.evaluation import (
    compare_behavioral_result,
    load_behavioral_corpus,
    load_node_code_corpus,
)
from notebook_to_kedro.evaluation.behavioral_execution import (
    BehavioralExecutionConfig,
    _result_from_worker,
    _worker_request,
)
from notebook_to_kedro.evaluation.behavioral_worker import run_worker_payload
from notebook_to_kedro.evaluation.node_body_benchmark import _corpus_sha256
from notebook_to_kedro.generation.code import (
    NodeBodyResponse,
    assemble_node_body,
    build_parameter_evidence,
)

if TYPE_CHECKING:
    from nbformat import NotebookNode

ROOT = Path(__file__).parents[2]
NODES = ROOT / "tests/fixtures/evaluation/node_code"
BEHAVIORS = ROOT / "tests/fixtures/evaluation/behavioral"


def test_fresh_corpus_identity_is_frozen_before_model_measurements() -> None:
    assert (
        _corpus_sha256(
            load_behavioral_corpus(BEHAVIORS / "v3"), load_node_code_corpus(NODES / "v3")
        )
        == "1a4fade0462bc0ef58a18cea70099079ff9dd09f8980fb697c5cb64794e32125"
    )


def test_fresh_corpus_has_disjoint_identities_sources_and_explicit_interfaces() -> None:
    nodes = load_node_code_corpus(NODES / "v3")
    behaviors = load_behavioral_corpus(BEHAVIORS / "v3")
    prior_nodes = (*load_node_code_corpus(NODES / "v1"), *load_node_code_corpus(NODES / "v2"))
    prior_behaviors = (
        *load_behavioral_corpus(BEHAVIORS / "v1"),
        *load_behavioral_corpus(BEHAVIORS / "v2"),
    )
    assert {node.case_id for node in nodes} == {
        "normalize-tags",
        "partition-measurements",
        "cumulative-balance",
        "rank-candidates",
    }
    for attr in ("case_id", "notebook_path"):
        assert {getattr(node, attr) for node in nodes}.isdisjoint(
            getattr(node, attr) for node in prior_nodes
        )
    for attr in ("request_id", "task_id", "raw_source"):
        assert {getattr(node.request, attr) for node in nodes}.isdisjoint(
            getattr(node.request, attr) for node in prior_nodes
        )
    assert {case.case_id for case in behaviors}.isdisjoint(case.case_id for case in prior_behaviors)
    for node in nodes:
        notebook = cast(
            "NotebookNode",
            nbformat.read(ROOT / node.notebook_path, as_version=4),  # type: ignore[no-untyped-call]
        )
        nbformat.validate(notebook)
        for cell in notebook.cells:
            if cell.cell_type == "code":
                assert cell.execution_count is None
                assert cell.outputs == []
        source = ast.parse(node.request.raw_source)
        assert len(source.body) == len(node.request.statement_ids)
        assert build_parameter_evidence(node.request) == ()
        assert len(node.invalid_examples) == 2
        linked = [case for case in behaviors if case.node_code_case_id == node.case_id]
        assert len(linked) == 3
        assert sum(case.expected_exception is not None for case in linked) == 1


def test_fresh_approved_bodies_reconstruct_the_hand_authored_references() -> None:
    for node in load_node_code_corpus(NODES / "v3"):
        function = ast.parse(node.reference_response.function_code).body[0]
        assert isinstance(function, ast.FunctionDef)
        body = ast.unparse(ast.Module(body=function.body[:-1], type_ignores=[]))
        assembled = assemble_node_body(
            node.request,
            NodeBodyResponse("1.0", node.request.request_id, node.request.task_id, body),
        )
        assert ast.dump(ast.parse(assembled.function_code)) == ast.dump(
            ast.parse(node.reference_response.function_code)
        )
        assert assembled.imports == node.reference_response.imports


@pytest.mark.integration
@pytest.mark.parametrize(
    ("node_id", "invalid_id", "scenario_id"),
    [
        ("normalize-tags", "lower-instead-of-casefold", "normalize-tags-standard"),
        ("normalize-tags", "omitted-whitespace-trimming", "normalize-tags-standard"),
        ("partition-measurements", "exclusive-boundary", "partition-measurements-standard"),
        (
            "partition-measurements",
            "omitted-limit-validation",
            "partition-measurements-negative-limit",
        ),
        ("cumulative-balance", "recorded-zero-amount", "cumulative-balance-standard"),
        ("cumulative-balance", "omitted-overdraft-check", "cumulative-balance-overdraft"),
        ("rank-candidates", "ascending-score", "rank-candidates-standard"),
        ("rank-candidates", "retained-source-index", "rank-candidates-standard"),
    ],
)
def test_fresh_scenarios_detect_each_checked_in_negative_control(
    node_id: str, invalid_id: str, scenario_id: str
) -> None:
    node = next(case for case in load_node_code_corpus(NODES / "v3") if case.case_id == node_id)
    scenario = next(
        case for case in load_behavioral_corpus(BEHAVIORS / "v3") if case.case_id == scenario_id
    )
    negative = next(item.response for item in node.invalid_examples if item.id == invalid_id)
    # This bypass is only for fixed negative fixtures, never provider proposals.
    payload = _worker_request(scenario, node.request, negative, BehavioralExecutionConfig())
    result = _result_from_worker(run_worker_payload(payload), duration=0.0)
    comparison = compare_behavioral_result(scenario, result)
    assert comparison.status == "mismatch", comparison

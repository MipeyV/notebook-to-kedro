import ast
from pathlib import Path

import pytest

from notebook_to_kedro.evaluation import (
    behavioral_corpus_comparison_to_dict,
    compare_behavioral_corpus,
    compare_behavioral_result,
    evaluate_behavioral_proposal,
    execute_behavioral_reference,
    load_behavioral_corpus,
    load_node_code_corpus,
    run_behavioral_code_benchmark,
)
from notebook_to_kedro.evaluation.behavioral_execution import (
    BehavioralExecutionConfig,
    _result_from_worker,
    _worker_request,
)
from notebook_to_kedro.evaluation.behavioral_worker import run_worker_payload
from notebook_to_kedro.generation.code import NodeBodyResponse, NodeCodeRequest, assemble_node_body


@pytest.mark.integration
def test_assembled_reviewed_bodies_match_all_seventeen_scenarios() -> None:
    nodes = load_node_code_corpus(Path("tests/fixtures/evaluation/node_code/v2"))
    behaviors = load_behavioral_corpus(Path("tests/fixtures/evaluation/behavioral/v2"))
    assert len(nodes) == 8
    assert len(behaviors) == 17
    for node in nodes:
        function = ast.parse(node.reference_response.function_code).body[0]
        assert isinstance(function, ast.FunctionDef)
        body = ast.unparse(ast.Module(body=function.body[:-1], type_ignores=[]))
        response = assemble_node_body(
            node.request,
            NodeBodyResponse("1.0", node.request.request_id, node.request.task_id, body),
        )
        scenarios = [case for case in behaviors if case.node_code_case_id == node.case_id]
        assert scenarios
        for scenario in scenarios:
            with pytest.raises(ValueError, match="allow_untrusted_code_execution=True"):
                evaluate_behavioral_proposal(scenario, node, response)
            evaluation = evaluate_behavioral_proposal(
                scenario, node, response, allow_untrusted_code_execution=True
            )
            assert evaluation.matched, evaluation.comparison


@pytest.mark.integration
@pytest.mark.parametrize(("version", "scenario_count", "node_count"), [("v1", 5, 4), ("v2", 17, 8)])
def test_all_reviewed_behavioral_references_execute_in_isolated_workers(
    version: str, scenario_count: int, node_count: int
) -> None:
    behaviors = load_behavioral_corpus(Path("tests/fixtures/evaluation/behavioral") / version)
    nodes = {
        case.case_id: case
        for case in load_node_code_corpus(Path("tests/fixtures/evaluation/node_code") / version)
    }

    results = tuple(
        execute_behavioral_reference(case, nodes[case.node_code_case_id]) for case in behaviors
    )

    assert tuple(result.case_id for result in results) == tuple(case.case_id for case in behaviors)
    assert tuple(result.status for result in results) == tuple(
        "exception" if case.expected_exception is not None else "success" for case in behaviors
    )

    report = compare_behavioral_corpus(behaviors, results)
    payload = behavioral_corpus_comparison_to_dict(report)

    assert report.exact_match, tuple(case for case in report.cases if case.status != "matched")
    assert report.matched_count == scenario_count
    assert report.mismatch_count == 0
    assert report.execution_error_count == 0
    assert payload["match_rate"] == 1.0

    proposal_evaluations = tuple(
        evaluate_behavioral_proposal(
            case,
            nodes[case.node_code_case_id],
            nodes[case.node_code_case_id].reference_response,
            allow_untrusted_code_execution=True,
        )
        for case in behaviors
    )

    assert all(evaluation.matched for evaluation in proposal_evaluations), tuple(
        evaluation.comparison for evaluation in proposal_evaluations if not evaluation.matched
    )
    assert len({evaluation.response_sha256 for evaluation in proposal_evaluations}) == node_count


@pytest.mark.integration
def test_expanded_benchmark_requests_each_node_once_and_evaluates_every_scenario() -> None:
    root = Path(__file__).parents[2]
    behaviors = load_behavioral_corpus(root / "tests/fixtures/evaluation/behavioral/v2")
    nodes = load_node_code_corpus(root / "tests/fixtures/evaluation/node_code/v2")

    class ReferenceProvider:
        provider_name = "approved-reference"
        model_name = "offline"

        def __init__(self) -> None:
            self.requests: list[str] = []

        def complete(self, request: NodeCodeRequest) -> str:
            self.requests.append(request.request_id)
            node = next(case for case in nodes if case.request.request_id == request.request_id)
            return node.reference_response.to_json()

    provider = ReferenceProvider()
    report = run_behavioral_code_benchmark(
        behaviors,
        nodes,
        provider,
        project_root=root,
        allow_untrusted_code_execution=True,
    )

    assert len(provider.requests) == len(set(provider.requests)) == 8
    assert all(proposal.status == "accepted" for proposal in report.proposals)
    evaluations = tuple(
        evaluation for proposal in report.proposals for evaluation in proposal.evaluations
    )
    assert len(evaluations) == report.scenario_count == 17
    assert all(evaluation.matched for evaluation in evaluations), tuple(
        evaluation.comparison for evaluation in evaluations if not evaluation.matched
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("node_id", "invalid_id", "scenario_id"),
    [
        ("aggregate-orders", "count-drops-missing-amounts", "aggregate-orders-refunds-and-missing"),
        ("aggregate-orders", "changed-group-order", "aggregate-orders-standard"),
        ("join-customers", "inner-join-drops-orders", "join-customers-standard"),
        ("join-customers", "omitted-key-validation", "join-customers-duplicate-key"),
        ("encode-categories", "dropped-baseline-category", "encode-categories-standard"),
        ("encode-categories", "changed-indicator-dtype", "encode-categories-standard"),
        ("date-features", "silently-coerced-invalid-dates", "date-features-invalid-date"),
        ("date-features", "changed-weekday-origin", "date-features-standard"),
    ],
)
def test_expanded_scenarios_detect_known_semantic_changes(
    node_id: str, invalid_id: str, scenario_id: str
) -> None:
    root = Path(__file__).parents[2]
    nodes = load_node_code_corpus(root / "tests/fixtures/evaluation/node_code/v2")
    behaviors = load_behavioral_corpus(root / "tests/fixtures/evaluation/behavioral/v2")
    node = next(case for case in nodes if case.case_id == node_id)
    scenario = next(case for case in behaviors if case.case_id == scenario_id)
    negative_control = next(
        item.response for item in node.invalid_examples if item.id == invalid_id
    )

    # Only checked-in negative controls bypass static rejection to test scenario sensitivity.
    payload = _worker_request(scenario, node.request, negative_control, BehavioralExecutionConfig())
    result = _result_from_worker(run_worker_payload(payload), duration=0.0)
    comparison = compare_behavioral_result(scenario, result)

    assert comparison.status == "mismatch", comparison

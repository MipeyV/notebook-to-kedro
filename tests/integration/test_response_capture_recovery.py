from __future__ import annotations

import ast
from pathlib import Path

import pytest

from notebook_to_kedro.evaluation import (
    BehavioralBenchmarkConfiguration,
    CorpusBoundCodeBenchmarkReport,
    NodeBodyBenchmarkReport,
    collect_environment_provenance,
    create_response_capture,
    load_behavioral_corpus,
    load_node_code_corpus,
    load_response_capture,
    recover_response_capture,
)
from notebook_to_kedro.generation.code import NodeBodyResponse, NodeCodeRequest


@pytest.mark.integration
@pytest.mark.parametrize("proposal_format", ["full-code", "bound-full-code", "node-body"])
def test_complete_reference_captures_recover_in_real_workers(
    tmp_path: Path,
    proposal_format: str,
) -> None:
    root = Path(__file__).parents[2]
    behaviors = load_behavioral_corpus(root / "tests/fixtures/evaluation/behavioral/v3")
    nodes = load_node_code_corpus(root / "tests/fixtures/evaluation/node_code/v3")

    class ReferenceProvider:
        provider_name = "offline-reference"
        model_name = "reviewed-functions"
        prompt_version = "node-body-v1" if proposal_format == "node-body" else "node-code-v4"

        def __init__(self) -> None:
            self.calls = 0

        def complete(self, request: NodeCodeRequest) -> str:
            self.calls += 1
            node = next(node for node in nodes if node.request == request)
            if proposal_format != "node-body":
                return node.reference_response.to_json()
            function = ast.parse(node.reference_response.function_code).body[0]
            assert isinstance(function, ast.FunctionDef)
            body = ast.unparse(ast.Module(body=function.body[:-1], type_ignores=[]))
            return NodeBodyResponse("1.0", request.request_id, request.task_id, body).to_json()

    provider = ReferenceProvider()
    adapter = create_response_capture(
        tmp_path / "capture",
        behaviors,
        nodes,
        provider,
        provenance=collect_environment_provenance(project_root=root),
        configuration=BehavioralBenchmarkConfiguration(
            "http://localhost:11434", 120, include_parameter_evidence=True
        ),
        prompt_version=provider.prompt_version,
        proposal_format=proposal_format,
        allow_untrusted_code_execution=True,
        project_root=root,
    )
    for node in nodes:
        adapter.complete(node.request)
    assert provider.calls == 4
    capture = load_response_capture(tmp_path / "capture")
    assert not capture.missing_node_code_case_ids
    report = recover_response_capture(
        capture, behaviors, nodes, allow_untrusted_code_execution=True, project_root=root
    )
    benchmark = (
        report.benchmark
        if isinstance(report, (NodeBodyBenchmarkReport, CorpusBoundCodeBenchmarkReport))
        else report
    )
    assert provider.calls == 4
    assert len(benchmark.proposals) == 4
    evaluations = [
        evaluation for proposal in benchmark.proposals for evaluation in proposal.evaluations
    ]
    assert len(evaluations) == benchmark.scenario_count == 12
    assert all(evaluation.matched for evaluation in evaluations)
    assert all(proposal.proposal_duration_seconds == 0 for proposal in benchmark.proposals)

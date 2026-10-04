"""Execute the reviewed body corpus and replay it without model calls."""

import ast
from pathlib import Path

import pytest

from notebook_to_kedro.evaluation import (
    BehavioralBenchmarkConfiguration,
    behavioral_code_benchmark_to_dict,
    collect_environment_provenance,
    create_node_body_benchmark_artifact,
    load_behavioral_corpus,
    load_node_body_benchmark_artifact,
    load_node_code_corpus,
    node_body_benchmark_artifact_sha256,
    replay_node_body_benchmark,
    run_node_body_benchmark,
    write_node_body_benchmark_artifact,
)
from notebook_to_kedro.generation.code import (
    NODE_BODY_PROMPT_VERSION,
    NodeBodyResponse,
    NodeCodeRequest,
)


@pytest.mark.integration
def test_reviewed_body_benchmark_and_offline_replay_match_seventeen_scenarios(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[2]
    behaviors = load_behavioral_corpus(root / "tests/fixtures/evaluation/behavioral/v2")
    nodes = load_node_code_corpus(root / "tests/fixtures/evaluation/node_code/v2")

    class ReferenceProvider:
        provider_name = "approved-body-reference"
        model_name = "offline"
        prompt_version = NODE_BODY_PROMPT_VERSION

        def __init__(self) -> None:
            self.requests: list[NodeCodeRequest] = []

        def complete(self, request: NodeCodeRequest) -> str:
            self.requests.append(request)
            node = next(node for node in nodes if node.request.request_id == request.request_id)
            function = ast.parse(node.reference_response.function_code).body[0]
            assert isinstance(function, ast.FunctionDef)
            body = ast.unparse(ast.Module(body=function.body[:-1], type_ignores=[]))
            return NodeBodyResponse("1.0", request.request_id, request.task_id, body).to_json()

    provider = ReferenceProvider()
    report = run_node_body_benchmark(
        behaviors, nodes, provider, allow_untrusted_code_execution=True, project_root=root
    )
    assert len(provider.requests) == 8
    assert report.benchmark.scenario_count == 17
    assert all(proposal.status == "accepted" for proposal in report.benchmark.proposals)
    assert all(
        evaluation.matched
        for proposal in report.benchmark.proposals
        for evaluation in proposal.evaluations
    )
    configuration = BehavioralBenchmarkConfiguration(
        "http://localhost:11434", 120, include_parameter_evidence=True
    )
    provenance = collect_environment_provenance(project_root=root)
    artifact = create_node_body_benchmark_artifact(report, provenance, configuration)
    output = tmp_path / "reference-body-benchmark.json"
    write_node_body_benchmark_artifact(output, artifact)
    loaded = load_node_body_benchmark_artifact(output)
    replay = replay_node_body_benchmark(
        loaded, behaviors, nodes, allow_untrusted_code_execution=True, project_root=root
    )
    assert len(provider.requests) == 8
    summary = behavioral_code_benchmark_to_dict(replay.benchmark)["summary"]
    assert isinstance(summary, dict)
    assert summary["end_to_end_match_rate"] == 1.0
    replay_artifact = create_node_body_benchmark_artifact(
        replay,
        provenance,
        configuration,
        mode="replay",
        source_artifact_sha256=node_body_benchmark_artifact_sha256(loaded),
    )
    replay_output = tmp_path / "reference-body-replay.json"
    write_node_body_benchmark_artifact(replay_output, replay_artifact)
    assert load_node_body_benchmark_artifact(replay_output) == replay_artifact

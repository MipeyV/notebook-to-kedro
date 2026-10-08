"""Compare new full-code and body envelopes using references, never an LLM."""

import ast
from pathlib import Path
from typing import cast

import pytest

from notebook_to_kedro.evaluation import (
    BehavioralBenchmarkConfiguration,
    collect_environment_provenance,
    compare_generation_formats,
    corpus_bound_code_artifact_sha256,
    create_corpus_bound_code_artifact,
    create_node_body_benchmark_artifact,
    load_behavioral_corpus,
    load_corpus_bound_code_artifact,
    load_node_body_benchmark_artifact,
    load_node_code_corpus,
    replay_corpus_bound_code_benchmark,
    run_corpus_bound_code_benchmark,
    run_node_body_benchmark,
    write_corpus_bound_code_artifact,
    write_node_body_benchmark_artifact,
)
from notebook_to_kedro.exceptions import BehavioralBenchmarkArtifactError
from notebook_to_kedro.generation.code import NodeBodyResponse, NodeCodeRequest


@pytest.mark.integration
def test_fresh_reference_formats_archive_replay_and_compare_offline(tmp_path: Path) -> None:
    root = Path(__file__).parents[2]
    behaviors = load_behavioral_corpus(root / "tests/fixtures/evaluation/behavioral/v3")
    nodes = load_node_code_corpus(root / "tests/fixtures/evaluation/node_code/v3")

    class ReferenceProvider:
        provider_name = "approved-reference"
        model_name = "offline"

        def __init__(self, *, body: bool) -> None:
            self.body = body
            self.prompt_version = "offline-body" if body else "offline-full"
            self.requests: list[NodeCodeRequest] = []

        def complete(self, request: NodeCodeRequest) -> str:
            self.requests.append(request)
            node = next(node for node in nodes if node.request.request_id == request.request_id)
            if not self.body:
                return node.reference_response.to_json()
            function = ast.parse(node.reference_response.function_code).body[0]
            assert isinstance(function, ast.FunctionDef)
            body = ast.unparse(ast.Module(body=function.body[:-1], type_ignores=[]))
            return NodeBodyResponse("1.0", request.request_id, request.task_id, body).to_json()

    configuration = BehavioralBenchmarkConfiguration(
        "http://localhost:11434", 120, include_parameter_evidence=True
    )
    provenance = collect_environment_provenance(project_root=root)
    full_provider, body_provider = ReferenceProvider(body=False), ReferenceProvider(body=True)
    full_report = run_corpus_bound_code_benchmark(
        behaviors,
        nodes,
        full_provider,
        prompt_version="offline-full",
        allow_untrusted_code_execution=True,
        project_root=root,
    )
    body_report = run_node_body_benchmark(
        behaviors,
        nodes,
        body_provider,
        allow_untrusted_code_execution=True,
        project_root=root,
    )
    full = create_corpus_bound_code_artifact(full_report, provenance, configuration)
    body = create_node_body_benchmark_artifact(body_report, provenance, configuration)
    full_path, body_path = tmp_path / "full.json", tmp_path / "body.json"
    write_corpus_bound_code_artifact(full_path, full)
    write_node_body_benchmark_artifact(body_path, body)
    full, body = (
        load_corpus_bound_code_artifact(full_path),
        load_node_body_benchmark_artifact(body_path),
    )
    assert (
        full.corpus_sha256
        == body.corpus_sha256
        == "1a4fade0462bc0ef58a18cea70099079ff9dd09f8980fb697c5cb64794e32125"
    )
    with pytest.raises(BehavioralBenchmarkArtifactError, match="known ollama_version"):
        compare_generation_formats(full, body)
    replay_report = replay_corpus_bound_code_benchmark(
        full, behaviors, nodes, allow_untrusted_code_execution=True, project_root=root
    )
    replay = create_corpus_bound_code_artifact(
        replay_report,
        provenance,
        configuration,
        mode="replay",
        source_artifact_sha256=corpus_bound_code_artifact_sha256(full),
    )
    replay_path = tmp_path / "replay.json"
    write_corpus_bound_code_artifact(replay_path, replay)
    comparison = compare_generation_formats(load_corpus_bound_code_artifact(replay_path), body)
    assert len(full_provider.requests) == len(body_provider.requests) == 4
    assert comparison["comparison_scope"] == "outcomes-only"
    assert comparison["regressed_proposal_count"] == comparison["regressed_scenario_count"] == 0
    assert len(cast("list[object]", comparison["scenario_changes"])) == 12
    for name in ("baseline_summary", "candidate_summary"):
        summary = cast("dict[str, object]", comparison[name])
        assert summary["accepted_count"] == 4
        assert summary["matched_scenario_count"] == 12
        assert summary["end_to_end_match_rate"] == 1.0
    assert (
        cast("dict[str, dict[str, object]]", comparison["metrics"])["provider_duration_seconds"][
            "delta"
        ]
        is None
    )

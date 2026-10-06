from __future__ import annotations

import ast
import json
import subprocess
from dataclasses import replace
from math import inf, nan
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from notebook_to_kedro import cli
from notebook_to_kedro.evaluation import (
    BehavioralBenchmarkConfiguration,
    BehavioralBenchmarkProvenance,
    BehavioralCase,
    NodeBodyBenchmarkArtifact,
    NodeBodyBenchmarkReport,
    NodeCodeCase,
    behavior_value_to_dict,
    behavioral_benchmark_artifact_from_json,
    behavioral_benchmark_artifact_to_json,
    behavioral_code_benchmark_to_dict,
    compare_node_body_benchmark_artifacts,
    create_node_body_benchmark_artifact,
    load_behavioral_corpus,
    load_node_body_benchmark_artifact,
    load_node_code_corpus,
    node_body_benchmark_artifact_from_dict,
    node_body_benchmark_artifact_from_json,
    node_body_benchmark_artifact_sha256,
    node_body_benchmark_artifact_to_dict,
    node_body_benchmark_artifact_to_json,
    replay_node_body_benchmark,
    run_node_body_benchmark,
    write_node_body_benchmark_artifact,
)
from notebook_to_kedro.evaluation.behavioral_artifacts import _json_sha256
from notebook_to_kedro.exceptions import BehavioralBenchmarkArtifactError, NodeCodeProviderError
from notebook_to_kedro.generation.code import (
    NODE_BODY_PROMPT_VERSION,
    NodeBodyResponse,
    NodeCodeRequest,
)

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = Path(__file__).parents[3]


class _Provider:
    provider_name = "offline-reference"
    model_name = "reviewed-bodies"
    prompt_version = NODE_BODY_PROMPT_VERSION

    def __init__(self, nodes: tuple[NodeCodeCase, ...]) -> None:
        self.requests: list[NodeCodeRequest] = []
        self.responses: dict[str, str | Exception] = {}
        for node in nodes:
            function = ast.parse(node.reference_response.function_code).body[0]
            assert isinstance(function, ast.FunctionDef)
            body = ast.unparse(ast.Module(body=function.body[:-1], type_ignores=[]))
            self.responses[node.request.request_id] = (
                "\n"
                + NodeBodyResponse(
                    "1.0", node.request.request_id, node.request.task_id, body
                ).to_json()
                + "\n"
            )

    def complete(self, request: NodeCodeRequest) -> str:
        self.requests.append(request)
        response = self.responses[request.request_id]
        if isinstance(response, Exception):
            raise response
        return response


class _Process:
    pid = 123

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        return 0

    def kill(self) -> None:
        return None


def _workers(monkeypatch: pytest.MonkeyPatch, behaviors: tuple[BehavioralCase, ...]) -> list[str]:
    cases = {case.case_id: case for case in behaviors}
    calls: list[str] = []

    def popen(command: tuple[str, ...], **_kwargs: object) -> subprocess.Popen[bytes]:
        payload = json.loads(Path(command[-3]).read_text(encoding="utf-8"))
        case = cases[payload["case_id"]]
        calls.append(case.case_id)
        expected = case.expected_exception
        result = {
            "schema_version": "1.0",
            "case_id": case.case_id,
            "node_code_case_id": case.node_code_case_id,
            "status": "exception" if expected else "success",
            "outputs": [
                {"output_name": item.output_name, "value": behavior_value_to_dict(item.value)}
                for item in case.expected_outputs
            ],
            "exception": None
            if expected is None
            else {
                "type_name": expected.type_name,
                "message": expected.message_contains or "expected exception",
            },
            "stdout": "",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "diagnostic_message": None,
        }
        Path(command[-2]).write_text(json.dumps(result), encoding="utf-8")
        return cast("subprocess.Popen[bytes]", _Process())

    monkeypatch.setattr(subprocess, "Popen", popen)
    return calls


@pytest.fixture
def nodes() -> tuple[NodeCodeCase, ...]:
    return load_node_code_corpus(ROOT / "tests/fixtures/evaluation/node_code/v1")


@pytest.fixture
def behaviors() -> tuple[BehavioralCase, ...]:
    return load_behavioral_corpus(ROOT / "tests/fixtures/evaluation/behavioral/v1")


def _artifact(report: NodeBodyBenchmarkReport, **kwargs: Any) -> NodeBodyBenchmarkArtifact:
    return create_node_body_benchmark_artifact(
        report,
        BehavioralBenchmarkProvenance(
            "2026-10-04T10:00:00Z", "abc123", "3.12.14", "win32", None, None
        ),
        BehavioralBenchmarkConfiguration(
            "http://localhost:11434", 120, include_parameter_evidence=True
        ),
        **kwargs,
    )


@pytest.fixture
def report(
    monkeypatch: pytest.MonkeyPatch,
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
) -> NodeBodyBenchmarkReport:
    _workers(monkeypatch, behaviors)
    return run_node_body_benchmark(
        behaviors,
        nodes,
        _Provider(nodes),
        allow_untrusted_code_execution=True,
        project_root=ROOT,
        clock=lambda: 0.0,
    )


@pytest.fixture
def artifact(report: NodeBodyBenchmarkReport) -> NodeBodyBenchmarkArtifact:
    return _artifact(report)


@pytest.fixture
def mixed(
    monkeypatch: pytest.MonkeyPatch,
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
) -> NodeBodyBenchmarkArtifact:
    _workers(monkeypatch, behaviors)
    provider = _Provider(nodes)
    provider.responses[nodes[0].request.request_id] = NodeCodeProviderError(
        "ollama_timeout", "timed out"
    )
    provider.responses[nodes[1].request.request_id] = "not-json"
    provider.responses[nodes[2].request.request_id] = NodeBodyResponse(
        "1.0", "wrong-id", nodes[2].request.task_id, nodes[2].request.raw_source
    ).to_json()
    return _artifact(
        run_node_body_benchmark(
            behaviors,
            nodes,
            provider,
            allow_untrusted_code_execution=True,
            project_root=ROOT,
            clock=lambda: 0.0,
        )
    )


def _mutate(
    artifact: NodeBodyBenchmarkArtifact, mutate: Callable[[dict[str, Any]], None]
) -> NodeBodyBenchmarkArtifact:
    payload: dict[str, Any] = json.loads(node_body_benchmark_artifact_to_json(artifact))
    mutate(payload)
    payload["benchmark"]["report_sha256"] = _json_sha256(payload["benchmark"]["report"])
    return node_body_benchmark_artifact_from_dict(payload)


@pytest.mark.parametrize(("version", "node_count", "scenario_count"), [("v1", 4, 5), ("v2", 8, 17)])
def test_body_benchmark_retains_raw_parsed_assembled_and_denominators(
    monkeypatch: pytest.MonkeyPatch, version: str, node_count: int, scenario_count: int
) -> None:
    nodes = load_node_code_corpus(ROOT / "tests/fixtures/evaluation/node_code" / version)
    behaviors = load_behavioral_corpus(ROOT / "tests/fixtures/evaluation/behavioral" / version)
    calls = _workers(monkeypatch, behaviors)
    provider = _Provider(nodes)
    ticks = iter(float(i) / 2 for i in range(node_count * 2))
    report = run_node_body_benchmark(
        behaviors,
        nodes,
        provider,
        allow_untrusted_code_execution=True,
        project_root=ROOT,
        clock=lambda: next(ticks),
    )
    payload = behavioral_code_benchmark_to_dict(report.benchmark)
    summary = cast("dict[str, object]", payload["summary"])
    assert len(provider.requests) == len(report.benchmark.proposals) == node_count
    assert len(calls) == scenario_count
    assert summary["proposal_count"] == summary["accepted_count"] == node_count
    assert summary["matched_scenario_count"] == scenario_count
    assert summary["end_to_end_match_rate"] == 1.0
    assert summary["provider_duration_seconds"] == node_count / 2
    assert report.benchmark.prompt_version == NODE_BODY_PROMPT_VERSION
    assert len(report.corpus_sha256) == 64
    for proposal, body in zip(report.benchmark.proposals, report.body_responses, strict=True):
        assert proposal.raw_response == provider.responses[proposal.request.request_id]
        assert body is not None
        assert proposal.response is not None
        assert body.request_id == proposal.request.request_id


def test_body_benchmark_retains_all_rejection_stages_and_not_evaluated_counts(
    mixed: NodeBodyBenchmarkArtifact,
) -> None:
    report = mixed.benchmark.report
    proposals = cast("list[dict[str, object]]", report["proposals"])
    assert [item["status"] for item in proposals] == [
        "provider_error",
        "invalid_response",
        "invalid_code",
        "accepted",
    ]
    assert proposals[0]["raw_response"] is None
    assert proposals[1]["raw_response"] == "not-json"
    assert proposals[2]["response"] is None
    assert mixed.body_responses[str(proposals[2]["node_code_case_id"])] is not None
    summary = cast("dict[str, object]", report["summary"])
    assert summary["accepted_count"] == 1
    assert (
        summary["provider_error_count"]
        == summary["invalid_response_count"]
        == summary["invalid_code_count"]
        == 1
    )
    assert summary["not_evaluated_scenario_count"] == 4
    assert summary["end_to_end_match_rate"] == 0.2


def test_body_benchmark_rejection_does_not_execute_marker(
    monkeypatch: pytest.MonkeyPatch,
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
    tmp_path: Path,
) -> None:
    calls = _workers(monkeypatch, behaviors)
    marker = tmp_path / "must-not-exist"
    provider = _Provider(nodes)
    for node in nodes:
        provider.responses[node.request.request_id] = NodeBodyResponse(
            "1.0",
            node.request.request_id,
            node.request.task_id,
            f"open({str(marker)!r}, 'w').close()\n" + node.request.raw_source,
        ).to_json()
    report = run_node_body_benchmark(
        behaviors, nodes, provider, allow_untrusted_code_execution=True, project_root=ROOT
    )
    assert all(item.status == "invalid_code" for item in report.benchmark.proposals)
    assert calls == []
    assert not marker.exists()


def test_body_benchmark_consent_and_preflight_fail_before_provider(
    behaviors: tuple[BehavioralCase, ...], nodes: tuple[NodeCodeCase, ...]
) -> None:
    provider = _Provider(nodes)
    for consent in (False, 1, "yes"):
        with pytest.raises(ValueError, match="allow_untrusted_code_execution=True"):
            run_node_body_benchmark(
                behaviors,
                nodes,
                provider,
                allow_untrusted_code_execution=cast("Any", consent),
                project_root=ROOT,
            )
    with pytest.raises(ValueError, match="source hash"):
        run_node_body_benchmark(
            behaviors,
            (replace(nodes[0], source_sha256="0" * 64), *nodes[1:]),
            provider,
            allow_untrusted_code_execution=True,
            project_root=ROOT,
        )
    assert provider.requests == []


@pytest.mark.parametrize("ticks", [(1.0, 0.0), (0.0, nan), (0.0, inf)])
def test_body_benchmark_rejects_invalid_clock(
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
    ticks: tuple[float, float],
) -> None:
    values = iter(ticks)
    with pytest.raises(ValueError, match="non-negative finite"):
        run_node_body_benchmark(
            behaviors,
            nodes,
            _Provider(nodes),
            allow_untrusted_code_execution=True,
            project_root=ROOT,
            clock=lambda: next(values),
        )


def test_body_benchmark_propagates_provider_bugs(
    behaviors: tuple[BehavioralCase, ...], nodes: tuple[NodeCodeCase, ...]
) -> None:
    provider = _Provider(nodes)
    provider.responses[nodes[0].request.request_id] = RuntimeError("provider bug")
    with pytest.raises(RuntimeError, match="provider bug"):
        run_node_body_benchmark(
            behaviors, nodes, provider, allow_untrusted_code_execution=True, project_root=ROOT
        )


def test_body_artifact_roundtrip_identity_and_format_separation(
    artifact: NodeBodyBenchmarkArtifact,
) -> None:
    payload = node_body_benchmark_artifact_to_dict(artifact)
    assert payload["artifact_kind"] == "node-body"
    assert node_body_benchmark_artifact_from_dict(payload) == artifact
    assert (
        node_body_benchmark_artifact_from_json(
            node_body_benchmark_artifact_to_json(artifact, indent=None)
        )
        == artifact
    )
    assert node_body_benchmark_artifact_sha256(artifact) == node_body_benchmark_artifact_sha256(
        artifact
    )
    assert len(node_body_benchmark_artifact_sha256(artifact)) == 64
    with pytest.raises(ValueError, match="fields"):
        behavioral_benchmark_artifact_from_json(node_body_benchmark_artifact_to_json(artifact))
    with pytest.raises(ValueError, match="fields"):
        node_body_benchmark_artifact_from_json(
            behavioral_benchmark_artifact_to_json(artifact.benchmark)
        )


@pytest.mark.parametrize("mode", ["live", "replay"])
def test_body_comparison_preserves_summaries_diagnostics_and_outer_identity(
    artifact: NodeBodyBenchmarkArtifact, mixed: NodeBodyBenchmarkArtifact, mode: str
) -> None:
    candidate = mixed
    if mode == "replay":
        candidate = replace(
            mixed,
            benchmark=replace(
                mixed.benchmark,
                mode="replay",
                source_artifact_sha256=node_body_benchmark_artifact_sha256(mixed),
            ),
        )
    comparison = compare_node_body_benchmark_artifacts(artifact, candidate)
    assert comparison["artifact_kind"] == "node-body-comparison"
    assert comparison["corpus_sha256"] == artifact.corpus_sha256
    assert comparison["baseline_artifact_sha256"] == node_body_benchmark_artifact_sha256(artifact)
    assert comparison["candidate_artifact_sha256"] == node_body_benchmark_artifact_sha256(candidate)
    assert comparison["baseline_summary"] == artifact.benchmark.report["summary"]
    assert comparison["candidate_summary"] == mixed.benchmark.report["summary"]
    assert comparison["regressed_proposal_count"] == 3
    data = cast("dict[str, Any]", comparison)
    assert data["candidate_metadata"]["mode"] == mode
    assert data["candidate_metadata"]["prompt_version"] == NODE_BODY_PROMPT_VERSION
    assert data["candidate_metadata"]["provenance"]["python_version"] == "3.12.14"
    latency = data["metrics"]["provider_duration_seconds"]
    assert latency["comparable"] is (mode == "live")
    assert latency["delta"] == (0.0 if mode == "live" else None)
    assert sum(row["candidate_code"] is not None for row in data["proposal_diagnostics"]) == 3
    assert data["candidate_summary"]["not_evaluated_scenario_count"] == 4


@pytest.mark.parametrize(
    "mutation",
    [
        "corpus",
        "execution",
        "validator",
        "policy",
        "count",
        "cases",
        "request",
        "source_sha256",
        "notebook_path",
    ],
)
def test_body_comparison_refuses_incompatible_evidence(
    artifact: NodeBodyBenchmarkArtifact, mixed: NodeBodyBenchmarkArtifact, mutation: str
) -> None:
    def mutate(data: dict[str, Any]) -> None:
        report = data["benchmark"]["report"]
        if mutation == "corpus":
            data["corpus_sha256"] = "0" * 64
        elif mutation == "execution":
            data["benchmark"]["configuration"]["execution"]["timeout_seconds"] = 3.0
        elif mutation == "validator":
            report["validator_version"] = "other"
        elif mutation == "policy":
            report["execution_policy"] = "other"
        elif mutation == "count":
            report["scenario_count"] += 1
        elif mutation == "cases":
            old = report["proposals"][0]["node_code_case_id"]
            report["proposals"][0]["node_code_case_id"] = "other-case"
            data["body_responses"]["other-case"] = data["body_responses"].pop(old)
        elif mutation == "request":
            report["proposals"][0]["request"]["raw_source"] = "changed = 1"
        else:
            report["proposals"][0][mutation] = (
                "0" * 64 if mutation == "source_sha256" else "other.ipynb"
            )

    changed = _mutate(mixed, mutate)
    with pytest.raises(
        BehavioralBenchmarkArtifactError, match=r"corpus|contracts|case IDs|sources"
    ):
        compare_node_body_benchmark_artifacts(artifact, changed)


def test_body_comparison_revalidates_mutable_contents(artifact: NodeBodyBenchmarkArtifact) -> None:
    artifact.benchmark.report["model_name"] = "tampered"
    with pytest.raises(ValueError, match="report_sha256"):
        compare_node_body_benchmark_artifacts(artifact, artifact)


def test_body_cli_run_replay_and_compare_with_real_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    nodes: tuple[NodeCodeCase, ...],
    behaviors: tuple[BehavioralCase, ...],
) -> None:
    provider = _Provider(nodes)
    monkeypatch.setattr(cli, "OllamaNodeBodyProvider", lambda *_args, **_kwargs: provider)
    monkeypatch.setattr(
        cli,
        "collect_environment_provenance",
        lambda **_kwargs: BehavioralBenchmarkProvenance(
            "2026-10-06T10:00:00Z", "abc123", "3.12.14", "win32", None, None
        ),
    )
    calls = _workers(monkeypatch, behaviors)
    run_path, replay_path = tmp_path / "run.json", tmp_path / "replay.json"
    corpus_args = [
        str(ROOT / "tests/fixtures/evaluation/behavioral/v1"),
        str(ROOT / "tests/fixtures/evaluation/node_code/v1"),
    ]
    options = ["--proposal-format", "node-body", "--project-root", str(ROOT)]
    run_args = [
        "behavioral-benchmark",
        "run",
        *corpus_args,
        str(run_path),
        *options,
        "--ollama-model",
        "offline",
        "--allow-untrusted-code-execution",
    ]
    assert cli.main(run_args) == 0
    assert len(provider.requests) == len(nodes)
    recorded = load_node_body_benchmark_artifact(run_path)
    assert recorded.benchmark.configuration.include_parameter_evidence is True

    def no_provider(*_args: object, **_kwargs: object) -> None:
        pytest.fail("replay and comparison must not invoke Ollama")

    monkeypatch.setattr(cli, "OllamaNodeBodyProvider", no_provider)
    monkeypatch.setattr("notebook_to_kedro.semantic.ollama.urlopen", no_provider)
    monkeypatch.setattr("notebook_to_kedro.evaluation.behavioral_artifacts.urlopen", no_provider)
    replay_args = [
        "behavioral-benchmark",
        "replay",
        str(run_path),
        *corpus_args,
        str(replay_path),
        *options,
        "--allow-untrusted-code-execution",
    ]
    assert cli.main(replay_args) == 0
    replayed = load_node_body_benchmark_artifact(replay_path)
    assert replayed.benchmark.source_artifact_sha256 == node_body_benchmark_artifact_sha256(
        recorded
    )
    assert len(calls) == len(behaviors) * 2
    capsys.readouterr()
    compare_args = [
        "behavioral-benchmark",
        "compare",
        str(run_path),
        str(replay_path),
        "--proposal-format",
        "node-body",
    ]
    assert cli.main(compare_args) == 0
    comparison = json.loads(capsys.readouterr().out)
    assert comparison["regressed_proposal_count"] == 0
    assert comparison["regressed_scenario_count"] == 0
    assert comparison["candidate_summary"]["matched_scenario_count"] == len(behaviors)
    assert comparison["metrics"]["provider_duration_seconds"]["delta"] is None
    output = tmp_path / "comparison.json"
    assert cli.main([*compare_args, "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8")) == comparison
    assert cli.main([*compare_args, "--output", str(output)]) == 1
    assert "already exists" in capsys.readouterr().err


@pytest.mark.parametrize("action", ["run", "replay"])
def test_body_cli_requires_execution_consent_without_provider_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    artifact: NodeBodyBenchmarkArtifact,
    action: str,
) -> None:
    nodes = load_node_code_corpus(ROOT / "tests/fixtures/evaluation/node_code/v1")
    provider = _Provider(nodes)
    monkeypatch.setattr(cli, "OllamaNodeBodyProvider", lambda *_args, **_kwargs: provider)
    source = tmp_path / "source.json"
    write_node_body_benchmark_artifact(source, artifact)
    output = tmp_path / "unauthorized.json"
    args = ["behavioral-benchmark", action]
    if action == "replay":
        args.append(str(source))
    args.extend(
        [
            str(ROOT / "tests/fixtures/evaluation/behavioral/v1"),
            str(ROOT / "tests/fixtures/evaluation/node_code/v1"),
            str(output),
            "--proposal-format",
            "node-body",
            "--project-root",
            str(ROOT),
        ]
    )
    if action == "run":
        args.extend(["--ollama-model", "offline"])
    assert cli.main(args) == 1
    assert "allow_untrusted_code_execution=True" in capsys.readouterr().err
    assert provider.requests == []
    assert not output.exists()


def test_body_cli_rejects_full_code_format_and_keeps_default_explicit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], artifact: NodeBodyBenchmarkArtifact
) -> None:
    body_path = tmp_path / "body.json"
    full_path = tmp_path / "full.json"
    write_node_body_benchmark_artifact(body_path, artifact)
    full_path.write_text(
        behavioral_benchmark_artifact_to_json(artifact.benchmark), encoding="utf-8"
    )
    assert (
        cli._parser()
        .parse_args(["behavioral-benchmark", "compare", str(full_path), str(full_path)])
        .proposal_format
        == "full-code"
    )
    assert (
        cli.main(
            [
                "behavioral-benchmark",
                "compare",
                str(body_path),
                str(full_path),
                "--proposal-format",
                "node-body",
            ]
        )
        == 1
    )
    assert "cannot load body benchmark artifact" in capsys.readouterr().err
    assert (
        cli.main(
            [
                "behavioral-benchmark",
                "compare",
                str(body_path),
                str(body_path),
            ]
        )
        == 1
    )
    assert "invalid behavioral benchmark artifact fields" in capsys.readouterr().err


@pytest.mark.parametrize(
    "payload",
    ["not-json", "[]", "{}", '{"x":1,"x":2}', '{"benchmark":{"mode":"live","mode":"replay"}}'],
)
def test_body_artifact_rejects_malformed_and_duplicate_json(payload: str) -> None:
    with pytest.raises(ValueError, match=r"Expecting|object|fields|duplicate"):
        node_body_benchmark_artifact_from_json(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "9"),
        ("artifact_kind", "full-code"),
        ("body_schema_version", "9"),
        ("assembly_version", "unknown"),
        ("parameter_evidence_version", "9"),
        ("corpus_sha256", "bad"),
        ("body_responses", {}),
        ("extra", True),
    ],
)
def test_body_artifact_rejects_unsupported_fields_and_versions(
    artifact: NodeBodyBenchmarkArtifact, field: str, value: object
) -> None:
    with pytest.raises(ValueError, match=r"version|artifact_kind|corpus_sha256|case IDs|fields"):
        _mutate(artifact, lambda data: data.__setitem__(field, value))


def test_body_artifact_requires_parameter_evidence_and_nonempty_prompt(
    artifact: NodeBodyBenchmarkArtifact,
) -> None:
    with pytest.raises(ValueError, match="exact parameter evidence"):
        _mutate(
            artifact,
            lambda data: data["benchmark"]["configuration"].update(
                {"include_parameter_evidence": False}
            ),
        )
    for prompt in (" ", None):

        def mutate_prompt(data: dict[str, Any], *, value: str | None = prompt) -> None:
            data["benchmark"]["report"]["prompt_version"] = value

        with pytest.raises(ValueError, match="prompt_version"):
            _mutate(artifact, mutate_prompt)


def test_body_artifact_checks_body_count(report: NodeBodyBenchmarkReport) -> None:
    with pytest.raises(ValueError, match="one body response"):
        _artifact(replace(report, body_responses=()))


@pytest.mark.parametrize("field", ["raw_response", "body", "response"])
def test_provider_errors_must_not_contain_model_data(
    mixed: NodeBodyBenchmarkArtifact, nodes: tuple[NodeCodeCase, ...], field: str
) -> None:
    def mutate(data: dict[str, Any]) -> None:
        item = data["benchmark"]["report"]["proposals"][0]
        if field == "body":
            data["body_responses"][nodes[0].case_id] = json.loads(
                NodeBodyResponse("1.0", "a", "b", "pass").to_json()
            )
        else:
            item[field] = "unexpected"

    with pytest.raises(ValueError, match="provider errors"):
        _mutate(mixed, mutate)


@pytest.mark.parametrize("mutation", ["body", "status", "response", "evaluations"])
def test_rejected_body_records_cannot_be_rewritten_as_executed(
    mixed: NodeBodyBenchmarkArtifact, nodes: tuple[NodeCodeCase, ...], mutation: str
) -> None:
    def mutate(data: dict[str, Any]) -> None:
        item = data["benchmark"]["report"]["proposals"][2]
        if mutation == "body":
            data["body_responses"][nodes[2].case_id]["review_notes"] = ["changed"]
        elif mutation == "status":
            item["status"] = "invalid_response"
        elif mutation == "response":
            item["response"] = json.loads(nodes[2].reference_response.to_json())
        else:
            item["evaluations"] = [{}]

    with pytest.raises(ValueError, match=r"raw response|assembled response|evaluations"):
        _mutate(mixed, mutate)


def test_invalid_json_cannot_be_labeled_as_invalid_code(mixed: NodeBodyBenchmarkArtifact) -> None:
    with pytest.raises(ValueError, match="raw response"):
        _mutate(
            mixed,
            lambda data: data["benchmark"]["report"]["proposals"][1].__setitem__(
                "status", "invalid_code"
            ),
        )


def test_accepted_cached_response_must_equal_reassembly(
    artifact: NodeBodyBenchmarkArtifact,
) -> None:
    with pytest.raises(ValueError, match="assembled response"):
        _mutate(
            artifact,
            lambda data: data["benchmark"]["report"]["proposals"][0]["response"].__setitem__(
                "review_notes", ["modified"]
            ),
        )


def test_artifact_write_load_exclusive_and_mutation_detection(
    tmp_path: Path, artifact: NodeBodyBenchmarkArtifact
) -> None:
    destination = tmp_path / "nested/body.json"
    write_node_body_benchmark_artifact(destination, artifact)
    assert load_node_body_benchmark_artifact(destination) == artifact
    with pytest.raises(BehavioralBenchmarkArtifactError, match="already exists"):
        write_node_body_benchmark_artifact(destination, artifact)
    artifact.benchmark.report["model_name"] = "tampered"
    with pytest.raises(ValueError, match="report_sha256"):
        write_node_body_benchmark_artifact(tmp_path / "tampered.json", artifact)
    assert not (tmp_path / "tampered.json").exists()


def test_body_loader_normalizes_file_and_validation_errors(tmp_path: Path) -> None:
    with pytest.raises(BehavioralBenchmarkArtifactError, match="cannot load"):
        load_node_body_benchmark_artifact(tmp_path / "missing.json")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json", encoding="utf-8")
    with pytest.raises(BehavioralBenchmarkArtifactError, match="cannot load"):
        load_node_body_benchmark_artifact(invalid)


def test_replay_uses_raw_bodies_offline_and_has_zero_provider_time(
    monkeypatch: pytest.MonkeyPatch,
    mixed: NodeBodyBenchmarkArtifact,
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
) -> None:
    def no_network(*_args: object, **_kwargs: object) -> None:
        pytest.fail("replay must not contact Ollama")

    monkeypatch.setattr("notebook_to_kedro.semantic.ollama.urlopen", no_network)
    monkeypatch.setattr("notebook_to_kedro.evaluation.behavioral_artifacts.urlopen", no_network)
    calls = _workers(monkeypatch, behaviors)
    report = replay_node_body_benchmark(
        mixed, behaviors, nodes, allow_untrusted_code_execution=True, project_root=ROOT
    )
    assert [item.status for item in report.benchmark.proposals] == [
        item["status"]
        for item in cast("list[dict[str, object]]", mixed.benchmark.report["proposals"])
    ]
    assert len(calls) == 1
    assert all(item.proposal_duration_seconds == 0.0 for item in report.benchmark.proposals)
    replay = _artifact(
        report, mode="replay", source_artifact_sha256=node_body_benchmark_artifact_sha256(mixed)
    )
    assert replay.benchmark.source_artifact_sha256 == node_body_benchmark_artifact_sha256(mixed)
    assert replay.benchmark.mode == "replay"
    assert (
        node_body_benchmark_artifact_from_json(node_body_benchmark_artifact_to_json(replay))
        == replay
    )


def test_replay_requires_consent_and_exact_corpus(
    artifact: NodeBodyBenchmarkArtifact,
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
) -> None:
    with pytest.raises(ValueError, match="allow_untrusted_code_execution=True"):
        replay_node_body_benchmark(artifact, behaviors, nodes, project_root=ROOT)
    changed = (replace(behaviors[0], case_id="changed-scenario"), *behaviors[1:])
    with pytest.raises(ValueError, match="exact recorded corpus"):
        replay_node_body_benchmark(
            artifact, changed, nodes, allow_untrusted_code_execution=True, project_root=ROOT
        )
    with pytest.raises(ValueError, match="exact recorded corpus"):
        replay_node_body_benchmark(
            artifact, behaviors, nodes[:-1], allow_untrusted_code_execution=True, project_root=ROOT
        )


@pytest.mark.parametrize("field", ["request", "source_sha256", "notebook_path"])
def test_replay_checks_recorded_source_binding(
    mixed: NodeBodyBenchmarkArtifact,
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
    field: str,
) -> None:
    def mutate(data: dict[str, Any]) -> None:
        item = data["benchmark"]["report"]["proposals"][0]
        if field == "request":
            item["request"]["raw_source"] = "changed = 1"
        else:
            item[field] = "0" * 64 if field == "source_sha256" else "other.ipynb"

    modified = _mutate(mixed, mutate)
    with pytest.raises(ValueError, match="source identity"):
        replay_node_body_benchmark(
            modified, behaviors, nodes, allow_untrusted_code_execution=True, project_root=ROOT
        )


@pytest.mark.parametrize("mutation", ["validator", "count", "missing"])
def test_replay_rejects_incompatible_versions_or_incomplete_records(
    mixed: NodeBodyBenchmarkArtifact,
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
    mutation: str,
) -> None:
    def mutate(data: dict[str, Any]) -> None:
        report = data["benchmark"]["report"]
        if mutation == "validator":
            report["validator_version"] = "unknown"
        elif mutation == "count":
            report["scenario_count"] = 0
        else:
            report["proposals"].pop(0)
            del data["body_responses"][nodes[0].case_id]

    modified = _mutate(mixed, mutate)
    with pytest.raises(ValueError, match=r"validator version|exact corpus"):
        replay_node_body_benchmark(
            modified, behaviors, nodes, allow_untrusted_code_execution=True, project_root=ROOT
        )


def test_corpus_identity_is_independent_of_case_order(
    monkeypatch: pytest.MonkeyPatch,
    artifact: NodeBodyBenchmarkArtifact,
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
) -> None:
    _workers(monkeypatch, behaviors)
    report = replay_node_body_benchmark(
        artifact,
        tuple(reversed(behaviors)),
        tuple(reversed(nodes)),
        allow_untrusted_code_execution=True,
        project_root=ROOT,
        execution_config=artifact.benchmark.configuration.execution,
    )
    assert report.corpus_sha256 == artifact.corpus_sha256

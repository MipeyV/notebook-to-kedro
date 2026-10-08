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
    CorpusBoundCodeBenchmarkArtifact,
    NodeBodyBenchmarkArtifact,
    NodeBodyBenchmarkReport,
    NodeCodeCase,
    behavior_value_to_dict,
    behavioral_benchmark_artifact_from_json,
    behavioral_benchmark_artifact_to_json,
    behavioral_code_benchmark_to_dict,
    compare_generation_formats,
    compare_node_body_benchmark_artifacts,
    corpus_bound_code_artifact_from_dict,
    corpus_bound_code_artifact_sha256,
    corpus_bound_code_artifact_to_dict,
    create_corpus_bound_code_artifact,
    create_node_body_benchmark_artifact,
    load_behavioral_corpus,
    load_corpus_bound_code_artifact,
    load_node_body_benchmark_artifact,
    load_node_code_corpus,
    node_body_benchmark_artifact_from_dict,
    node_body_benchmark_artifact_from_json,
    node_body_benchmark_artifact_sha256,
    node_body_benchmark_artifact_to_dict,
    node_body_benchmark_artifact_to_json,
    replay_corpus_bound_code_benchmark,
    replay_node_body_benchmark,
    run_corpus_bound_code_benchmark,
    run_node_body_benchmark,
    write_corpus_bound_code_artifact,
    write_node_body_benchmark_artifact,
)
from notebook_to_kedro.evaluation import corpus_bound_code as bound_module
from notebook_to_kedro.evaluation.behavioral_artifacts import _json_sha256
from notebook_to_kedro.evaluation.corpus_bound_code import validate_recorded_corpus
from notebook_to_kedro.evaluation.format_comparison import _validate_summary
from notebook_to_kedro.exceptions import BehavioralBenchmarkArtifactError, NodeCodeProviderError
from notebook_to_kedro.generation.code import (
    NODE_BODY_PROMPT_VERSION,
    NodeBodyResponse,
    NodeCodeRequest,
)

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = Path(__file__).parents[3]


class _FullProvider:
    provider_name = "offline-reference"
    model_name = "reviewed-bodies"
    prompt_version = "node-code-v4"

    def __init__(self, nodes: tuple[NodeCodeCase, ...]) -> None:
        self.requests: list[NodeCodeRequest] = []
        self.responses: dict[str, str | Exception] = {
            node.request.request_id: node.reference_response.to_json() for node in nodes
        }

    def complete(self, request: NodeCodeRequest) -> str:
        self.requests.append(request)
        response = self.responses[request.request_id]
        if isinstance(response, Exception):
            raise response
        return response


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


@pytest.fixture
def bound_artifact(
    monkeypatch: pytest.MonkeyPatch,
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
    artifact: NodeBodyBenchmarkArtifact,
) -> CorpusBoundCodeBenchmarkArtifact:
    _workers(monkeypatch, behaviors)
    report = run_corpus_bound_code_benchmark(
        behaviors,
        nodes,
        _FullProvider(nodes),
        allow_untrusted_code_execution=True,
        project_root=ROOT,
        prompt_version="node-code-v4",
        clock=lambda: 0.0,
    )
    return create_corpus_bound_code_artifact(
        report, artifact.benchmark.provenance, artifact.benchmark.configuration
    )


def _bound_payload(artifact: CorpusBoundCodeBenchmarkArtifact) -> dict[str, Any]:
    return cast(
        "dict[str, Any]", json.loads(json.dumps(corpus_bound_code_artifact_to_dict(artifact)))
    )


def _refresh_bound(payload: dict[str, Any]) -> CorpusBoundCodeBenchmarkArtifact:
    payload["corpus_sha256"] = _json_sha256(payload["corpus"])
    payload["benchmark"]["report_sha256"] = _json_sha256(payload["benchmark"]["report"])
    return corpus_bound_code_artifact_from_dict(payload)


def _live_pair(
    full: CorpusBoundCodeBenchmarkArtifact, body: NodeBodyBenchmarkArtifact
) -> tuple[CorpusBoundCodeBenchmarkArtifact, NodeBodyBenchmarkArtifact]:
    # Deliberately synthetic runtime identity, never evidence of a real model run.
    provenance = replace(
        full.benchmark.provenance, ollama_version="test-runtime", model_digest="a" * 64
    )
    return (
        replace(full, benchmark=replace(full.benchmark, provenance=provenance)),
        replace(body, benchmark=replace(body.benchmark, provenance=provenance)),
    )


def test_bound_artifact_roundtrip_and_shared_complete_identity(
    tmp_path: Path,
    bound_artifact: CorpusBoundCodeBenchmarkArtifact,
    artifact: NodeBodyBenchmarkArtifact,
) -> None:
    payload = corpus_bound_code_artifact_to_dict(bound_artifact)
    assert corpus_bound_code_artifact_from_dict(payload) == bound_artifact
    assert bound_artifact.corpus_sha256 == artifact.corpus_sha256
    assert corpus_bound_code_artifact_sha256(bound_artifact) == _json_sha256(payload)
    path = tmp_path / "nested/full.json"
    write_corpus_bound_code_artifact(path, bound_artifact)
    assert load_corpus_bound_code_artifact(path) == bound_artifact
    with pytest.raises(BehavioralBenchmarkArtifactError, match="already exists"):
        write_corpus_bound_code_artifact(path, bound_artifact)
    bound_artifact.benchmark.report["model_name"] = "tampered"
    with pytest.raises(ValueError, match="report_sha256"):
        write_corpus_bound_code_artifact(tmp_path / "tampered.json", bound_artifact)
    assert not (tmp_path / "tampered.json").exists()


@pytest.mark.parametrize(
    "payload",
    ["not-json", "[]", "{}", '{"x":1,"x":2}', '{"benchmark":{"mode":"live","mode":"replay"}}'],
)
def test_bound_loader_rejects_malformed_or_duplicate_json(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "bad.json"
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(BehavioralBenchmarkArtifactError, match="cannot load"):
        load_corpus_bound_code_artifact(path)


def test_bound_loader_rejects_missing_and_legacy_files(
    tmp_path: Path,
    bound_artifact: CorpusBoundCodeBenchmarkArtifact,
) -> None:
    with pytest.raises(BehavioralBenchmarkArtifactError, match="cannot load"):
        load_corpus_bound_code_artifact(tmp_path / "missing.json")
    path = tmp_path / "legacy.json"
    path.write_text(
        behavioral_benchmark_artifact_to_json(bound_artifact.benchmark), encoding="utf-8"
    )
    with pytest.raises(BehavioralBenchmarkArtifactError, match="fields"):
        load_corpus_bound_code_artifact(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "9"),
        ("artifact_kind", "full-code"),
        ("corpus_sha256", "invalid"),
        ("corpus_sha256", "0" * 64),
        ("extra", True),
        ("corpus", []),
    ],
)
def test_bound_envelope_rejects_invalid_fields(
    bound_artifact: CorpusBoundCodeBenchmarkArtifact,
    field: str,
    value: object,
) -> None:
    payload = _bound_payload(bound_artifact)
    payload[field] = value
    with pytest.raises(ValueError, match=r"version|artifact_kind|corpus_sha256|fields|object"):
        corpus_bound_code_artifact_from_dict(payload)


@pytest.mark.parametrize("mutation", ["extra", "array", "empty", "validator"])
def test_bound_snapshot_requires_complete_supported_corpus(
    bound_artifact: CorpusBoundCodeBenchmarkArtifact,
    mutation: str,
) -> None:
    data = _bound_payload(bound_artifact)
    if mutation == "extra":
        data["corpus"]["extra"] = True
    elif mutation == "array":
        data["corpus"]["nodes"] = {}
    elif mutation == "empty":
        data["corpus"] = {"behaviors": [], "nodes": []}
    else:
        data["benchmark"]["report"]["validator_version"] = "other"
    with pytest.raises(ValueError, match=r"fields|arrays|case|validator"):
        _refresh_bound(data)


@pytest.mark.parametrize(
    "mutation",
    [
        "count",
        "case",
        "request",
        "source_sha256",
        "notebook_path",
        "evaluations",
        "missing",
        "duplicate",
        "unknown",
        "comparison",
        "execution_identity",
    ],
)
def test_bound_records_require_exact_source_scenarios_and_comparison(
    bound_artifact: CorpusBoundCodeBenchmarkArtifact,
    mutation: str,
) -> None:
    data = _bound_payload(bound_artifact)
    report = data["benchmark"]["report"]
    proposal = report["proposals"][0]
    if mutation == "count":
        report["scenario_count"] += 1
    elif mutation == "case":
        proposal["node_code_case_id"] = "other"
    elif mutation == "request":
        proposal["request"]["raw_source"] = "changed = 1"
    elif mutation in ("source_sha256", "notebook_path"):
        proposal[mutation] = "0" * 64 if mutation == "source_sha256" else "changed.ipynb"
    elif mutation == "evaluations":
        proposal["evaluations"] = {}
    elif mutation == "missing":
        proposal["evaluations"].pop()
    elif mutation == "duplicate":
        proposal["evaluations"].append(proposal["evaluations"][0])
    elif mutation == "unknown":
        proposal["evaluations"][0]["case_id"] = "other"
    elif mutation == "comparison":
        proposal["evaluations"][0]["comparison"]["status"] = "mismatch"
    else:
        proposal["evaluations"][0]["execution"]["node_code_case_id"] = "other"
    with pytest.raises(ValueError, match=r"corpus|identity|array|scenarios|comparison"):
        _refresh_bound(data)


def test_recorded_corpus_explicitly_rejects_empty_inputs(
    bound_artifact: CorpusBoundCodeBenchmarkArtifact,
    nodes: tuple[NodeCodeCase, ...],
) -> None:
    with pytest.raises(ValueError, match="nodes and scenarios"):
        validate_recorded_corpus(bound_artifact.benchmark, (), nodes)


@pytest.mark.parametrize("mutation", ["raw", "response", "status"])
def test_bound_accepted_responses_are_revalidated_from_raw(
    bound_artifact: CorpusBoundCodeBenchmarkArtifact,
    mutation: str,
) -> None:
    data = _bound_payload(bound_artifact)
    proposal = data["benchmark"]["report"]["proposals"][0]
    if mutation == "raw":
        proposal["raw_response"] = None
    elif mutation == "response":
        proposal["response"]["review_notes"] = ["changed"]
    else:
        proposal["status"] = "invalid_code"
        proposal["evaluations"] = []
    with pytest.raises(ValueError, match=r"raw_response|raw full-code|evaluation identity"):
        _refresh_bound(data)


def test_bound_mixed_raw_validation_and_offline_replay(
    monkeypatch: pytest.MonkeyPatch,
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
    artifact: NodeBodyBenchmarkArtifact,
) -> None:
    provider = _FullProvider(nodes)
    provider.responses[nodes[0].request.request_id] = NodeCodeProviderError(
        "ollama_timeout", "timeout"
    )
    provider.responses[nodes[1].request.request_id] = "not-json"
    provider.responses[nodes[2].request.request_id] = replace(
        nodes[2].reference_response, request_id="wrong-id"
    ).to_json()
    calls = _workers(monkeypatch, behaviors)
    report = run_corpus_bound_code_benchmark(
        behaviors,
        nodes,
        provider,
        allow_untrusted_code_execution=True,
        project_root=ROOT,
        clock=lambda: 0.0,
    )
    full = create_corpus_bound_code_artifact(
        report, artifact.benchmark.provenance, artifact.benchmark.configuration
    )
    data = _bound_payload(full)
    proposals = data["benchmark"]["report"]["proposals"]
    assert [p["status"] for p in proposals] == [
        "provider_error",
        "invalid_response",
        "invalid_code",
        "accepted",
    ]
    assert proposals[2]["response"] is not None
    for index in (0, 1, 2):
        changed = _bound_payload(full)
        changed["benchmark"]["report"]["proposals"][index]["response"] = {"unexpected": True}
        with pytest.raises(ValueError, match=r"responses|raw full-code"):
            _refresh_bound(changed)
    changed = _bound_payload(full)
    changed["benchmark"]["report"]["proposals"][0]["raw_response"] = "unexpected"
    with pytest.raises(ValueError, match="provider errors"):
        _refresh_bound(changed)

    def no_network(*_args: object, **_kwargs: object) -> None:
        pytest.fail("replay must be offline")

    monkeypatch.setattr("notebook_to_kedro.semantic.ollama.urlopen", no_network)
    monkeypatch.setattr("notebook_to_kedro.evaluation.behavioral_artifacts.urlopen", no_network)
    replay = replay_corpus_bound_code_benchmark(
        full, behaviors, nodes, allow_untrusted_code_execution=True, project_root=ROOT
    )
    assert len(calls) == 2
    assert all(p.proposal_duration_seconds == 0.0 for p in replay.benchmark.proposals)
    replay_artifact = create_corpus_bound_code_artifact(
        replay,
        full.benchmark.provenance,
        full.benchmark.configuration,
        mode="replay",
        source_artifact_sha256=corpus_bound_code_artifact_sha256(full),
    )
    assert replay_artifact.benchmark.source_artifact_sha256 == corpus_bound_code_artifact_sha256(
        full
    )
    assert (
        corpus_bound_code_artifact_from_dict(corpus_bound_code_artifact_to_dict(replay_artifact))
        == replay_artifact
    )


def test_bound_run_and_replay_require_consent_and_exact_corpus(
    monkeypatch: pytest.MonkeyPatch,
    bound_artifact: CorpusBoundCodeBenchmarkArtifact,
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
) -> None:
    provider = _FullProvider(nodes)
    with pytest.raises(ValueError, match="allow_untrusted_code_execution=True"):
        run_corpus_bound_code_benchmark(behaviors, nodes, provider, project_root=ROOT)
    assert provider.requests == []
    with pytest.raises(ValueError, match="allow_untrusted_code_execution=True"):
        replay_corpus_bound_code_benchmark(bound_artifact, behaviors, nodes, project_root=ROOT)
    changed = (replace(behaviors[0], case_id="other"), *behaviors[1:])
    with pytest.raises(ValueError, match="exact recorded corpus"):
        replay_corpus_bound_code_benchmark(bound_artifact, changed, nodes)
    with pytest.raises(ValueError, match="exact recorded corpus"):
        replay_corpus_bound_code_benchmark(bound_artifact, behaviors, nodes[:-1])
    _workers(monkeypatch, behaviors)
    replay = replay_corpus_bound_code_benchmark(
        bound_artifact,
        tuple(reversed(behaviors)),
        tuple(reversed(nodes)),
        allow_untrusted_code_execution=True,
        project_root=ROOT,
        execution_config=bound_artifact.benchmark.configuration.execution,
    )
    assert replay.corpus_sha256 == bound_artifact.corpus_sha256


def test_format_comparison_records_live_controls_and_outer_hashes(
    bound_artifact: CorpusBoundCodeBenchmarkArtifact,
    artifact: NodeBodyBenchmarkArtifact,
    behaviors: tuple[BehavioralCase, ...],
) -> None:
    full, body = _live_pair(bound_artifact, artifact)
    comparison = compare_generation_formats(full, body)
    assert comparison["artifact_kind"] == "generation-format-comparison"
    assert comparison["comparison_scope"] == "recorded-live-controls"
    assert comparison["corpus_sha256"] == full.corpus_sha256
    assert comparison["baseline_artifact_sha256"] == corpus_bound_code_artifact_sha256(full)
    assert comparison["candidate_artifact_sha256"] == node_body_benchmark_artifact_sha256(body)
    assert comparison["regressed_scenario_count"] == 0
    rows = cast("list[dict[str, object]]", comparison["scenario_changes"])
    assert len(rows) == len(behaviors)
    assert all(row["change"] == "unchanged" for row in rows)
    assert (
        cast("dict[str, object]", comparison["baseline_metadata"])["prompt_version"]
        == "node-code-v4"
    )
    assert (
        cast("dict[str, object]", comparison["candidate_metadata"])["assembly_version"] is not None
    )


@pytest.mark.parametrize("field", ["repository_revision", "ollama_version", "model_digest"])
@pytest.mark.parametrize("missing", [False, True])
def test_live_format_comparison_requires_known_matching_identity(
    bound_artifact: CorpusBoundCodeBenchmarkArtifact,
    artifact: NodeBodyBenchmarkArtifact,
    field: str,
    *,
    missing: bool,
) -> None:
    full, body = _live_pair(bound_artifact, artifact)
    different = "b" * 64 if field == "model_digest" else "different"
    changes: dict[str, Any] = {field: None if missing else different}
    provenance = replace(body.benchmark.provenance, **changes)
    body = replace(body, benchmark=replace(body.benchmark, provenance=provenance))
    if missing:
        full = replace(full, benchmark=replace(full.benchmark, provenance=provenance))
    with pytest.raises(BehavioralBenchmarkArtifactError, match=field):
        compare_generation_formats(full, body)


@pytest.mark.parametrize("field", ["python_version", "platform"])
def test_format_comparison_rejects_runtime_difference(
    bound_artifact: CorpusBoundCodeBenchmarkArtifact,
    artifact: NodeBodyBenchmarkArtifact,
    field: str,
) -> None:
    full, body = _live_pair(bound_artifact, artifact)
    body = replace(
        body,
        benchmark=replace(
            body.benchmark, provenance=replace(body.benchmark.provenance, **{field: "different"})
        ),
    )
    with pytest.raises(BehavioralBenchmarkArtifactError, match="Python/platform"):
        compare_generation_formats(full, body)


@pytest.mark.parametrize(
    "mutation",
    [
        "corpus",
        "configuration",
        "provider_name",
        "model_name",
        "execution_policy",
        "source",
        "summary",
    ],
)
def test_format_comparison_rejects_incompatible_or_incoherent_evidence(
    bound_artifact: CorpusBoundCodeBenchmarkArtifact,
    artifact: NodeBodyBenchmarkArtifact,
    mutation: str,
) -> None:
    full, body = _live_pair(bound_artifact, artifact)

    def mutate(data: dict[str, Any]) -> None:
        if mutation == "corpus":
            data["corpus_sha256"] = "0" * 64
        elif mutation == "configuration":
            data["benchmark"]["configuration"]["provider_timeout_seconds"] = 1.0
        elif mutation == "source":
            data["benchmark"]["report"]["proposals"][0]["notebook_path"] = "other.ipynb"
        elif mutation == "summary":
            data["benchmark"]["report"]["summary"]["matched_scenario_count"] = 0
        else:
            data["benchmark"]["report"][mutation] = "different"

    changed = _mutate(body, mutate)
    with pytest.raises(ValueError, match=r"corpus|settings|identity|counts"):
        compare_generation_formats(full, changed)


def test_format_comparison_includes_rejected_scenarios_and_hides_replay_latency(
    bound_artifact: CorpusBoundCodeBenchmarkArtifact,
    mixed: NodeBodyBenchmarkArtifact,
    behaviors: tuple[BehavioralCase, ...],
) -> None:
    full = replace(
        bound_artifact,
        benchmark=replace(bound_artifact.benchmark, mode="replay", source_artifact_sha256="a" * 64),
    )
    comparison = compare_generation_formats(full, mixed)
    assert comparison["comparison_scope"] == "outcomes-only"
    assert (
        cast("dict[str, Any]", comparison["metrics"])["provider_duration_seconds"]["delta"] is None
    )
    assert comparison["regressed_proposal_count"] == 3
    assert comparison["regressed_scenario_count"] == 4
    assert len(cast("list[object]", comparison["scenario_changes"])) == len(behaviors)
    assert len(cast("list[object]", comparison["proposal_diagnostics"])) == 4


def test_format_comparison_keeps_both_rejected_scenarios_in_denominator(
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
    artifact: NodeBodyBenchmarkArtifact,
) -> None:
    full_provider, body_provider = _FullProvider(nodes), _Provider(nodes)
    for node in nodes:
        full_provider.responses[node.request.request_id] = "not-json"
        body_provider.responses[node.request.request_id] = "not-json"
    full_report = run_corpus_bound_code_benchmark(
        behaviors,
        nodes,
        full_provider,
        allow_untrusted_code_execution=True,
        project_root=ROOT,
        clock=lambda: 0.0,
    )
    body_report = run_node_body_benchmark(
        behaviors,
        nodes,
        body_provider,
        allow_untrusted_code_execution=True,
        project_root=ROOT,
        clock=lambda: 0.0,
    )
    full = create_corpus_bound_code_artifact(
        full_report, artifact.benchmark.provenance, artifact.benchmark.configuration
    )
    full, body = _live_pair(full, _artifact(body_report))
    comparison = compare_generation_formats(full, body)
    rows = cast("list[dict[str, object]]", comparison["scenario_changes"])
    assert len(rows) == len(behaviors)
    assert all(row["baseline_status"] == row["candidate_status"] == "not_evaluated" for row in rows)
    assert comparison["regressed_scenario_count"] == 0
    assert cast("dict[str, object]", comparison["candidate_summary"])["end_to_end_match_rate"] == 0


def test_format_summary_rejects_empty_proposals_and_unknown_status(
    bound_artifact: CorpusBoundCodeBenchmarkArtifact,
) -> None:
    for empty in (False, True):
        payload = json.loads(behavioral_benchmark_artifact_to_json(bound_artifact.benchmark))
        if empty:
            payload["report"]["proposals"] = []
        else:
            payload["report"]["proposals"][0]["evaluations"][0]["comparison"]["status"] = "unknown"
        payload["report_sha256"] = _json_sha256(payload["report"])
        decoded = behavioral_benchmark_artifact_from_json(json.dumps(payload))
        with pytest.raises(ValueError, match="nonempty proposals and known"):
            _validate_summary(decoded)


def test_bound_cli_run_replay_compare_and_no_implicit_migration(  # noqa: PLR0913, PLR0917
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    nodes: tuple[NodeCodeCase, ...],
    behaviors: tuple[BehavioralCase, ...],
    artifact: NodeBodyBenchmarkArtifact,
) -> None:
    provider = _FullProvider(nodes)
    monkeypatch.setattr(cli, "OllamaNodeCodeProvider", lambda *_args, **_kwargs: provider)
    monkeypatch.setattr(
        cli, "collect_environment_provenance", lambda **_kwargs: artifact.benchmark.provenance
    )
    calls = _workers(monkeypatch, behaviors)
    source, replay_path, body_path = (
        tmp_path / name for name in ("full.json", "replay.json", "body.json")
    )
    corpus = [
        str(ROOT / "tests/fixtures/evaluation/behavioral/v1"),
        str(ROOT / "tests/fixtures/evaluation/node_code/v1"),
    ]
    options = ["--proposal-format", "bound-full-code", "--project-root", str(ROOT)]
    run = [
        "behavioral-benchmark",
        "run",
        *corpus,
        str(source),
        *options,
        "--ollama-model",
        "offline",
        "--include-parameter-evidence",
    ]
    assert cli.main(run) == 1
    assert "allow_untrusted_code_execution=True" in capsys.readouterr().err
    assert provider.requests == []
    assert cli.main([*run, "--allow-untrusted-code-execution"]) == 0
    recorded = load_corpus_bound_code_artifact(source)
    assert len(provider.requests) == len(nodes)

    def no_provider(*_args: object, **_kwargs: object) -> None:
        pytest.fail("no provider calls during replay or comparison")

    monkeypatch.setattr(cli, "OllamaNodeCodeProvider", no_provider)
    monkeypatch.setattr("notebook_to_kedro.evaluation.behavioral_artifacts.urlopen", no_provider)
    replay = ["behavioral-benchmark", "replay", str(source), *corpus, str(replay_path), *options]
    assert cli.main(replay) == 1
    assert cli.main([*replay, "--allow-untrusted-code-execution"]) == 0
    replayed = load_corpus_bound_code_artifact(replay_path)
    assert replayed.benchmark.source_artifact_sha256 == corpus_bound_code_artifact_sha256(recorded)
    assert len(calls) == len(behaviors) * 2
    write_node_body_benchmark_artifact(body_path, artifact)
    capsys.readouterr()
    compare = ["behavioral-benchmark", "compare-formats", str(replay_path), str(body_path)]
    assert cli.main(compare) == 0
    comparison = json.loads(capsys.readouterr().out)
    assert comparison["comparison_scope"] == "outcomes-only"
    output = tmp_path / "comparison.json"
    assert cli.main([*compare, "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8")) == comparison
    assert cli.main([*compare, "--output", str(output)]) == 1
    assert "already exists" in capsys.readouterr().err
    legacy = tmp_path / "legacy.json"
    legacy.write_text(behavioral_benchmark_artifact_to_json(recorded.benchmark), encoding="utf-8")
    assert cli.main(["behavioral-benchmark", "compare-formats", str(legacy), str(body_path)]) == 1
    assert "fields" in capsys.readouterr().err


@pytest.mark.parametrize(
    "mutation",
    [
        "proposal-field",
        "evaluation-field",
        "evaluation-version",
        "node-id",
        "request-id",
        "task-id",
        "response-hash",
        "negative-duration",
        "infinite-duration",
        "missing-execution-duration",
    ],
)
def test_bound_records_reject_incomplete_identity_and_invalid_duration(
    bound_artifact: CorpusBoundCodeBenchmarkArtifact,
    mutation: str,
) -> None:
    payload = _bound_payload(bound_artifact)
    proposal = payload["benchmark"]["report"]["proposals"][0]
    row = proposal["evaluations"][0]
    if mutation == "proposal-field":
        del proposal["raw_response"]
    elif mutation == "evaluation-field":
        del row["response_sha256"]
    elif mutation == "evaluation-version":
        row["schema_version"] = "9"
    elif mutation in ("node-id", "request-id", "task-id", "response-hash"):
        field = {
            "node-id": "node_code_case_id",
            "request-id": "request_id",
            "task-id": "task_id",
            "response-hash": "response_sha256",
        }[mutation]
        row[field] = "other"
    elif mutation == "missing-execution-duration":
        del row["execution"]["duration_seconds"]
    else:
        proposal["proposal_duration_seconds"] = -1 if mutation == "negative-duration" else inf
    with pytest.raises(ValueError, match=r"fields|identity|duration|JSON"):
        _refresh_bound(payload)


@pytest.mark.parametrize(
    "field",
    [
        "accepted_count",
        "end_to_end_match_rate",
        "provider_duration_seconds",
        "mean_provider_duration_seconds",
        "execution_duration_seconds",
    ],
)
def test_format_comparison_rejects_inconsistent_counts_rates_and_timings(
    bound_artifact: CorpusBoundCodeBenchmarkArtifact,
    artifact: NodeBodyBenchmarkArtifact,
    field: str,
) -> None:
    full, body = _live_pair(bound_artifact, artifact)

    def mutate(payload: dict[str, Any]) -> None:
        summary = payload["benchmark"]["report"]["summary"]
        summary[field] += 1

    changed = _mutate(body, mutate)
    with pytest.raises(ValueError, match="counts and rates"):
        compare_generation_formats(full, changed)


def test_bound_corpus_capture_precedes_every_provider_call(
    monkeypatch: pytest.MonkeyPatch,
    nodes: tuple[NodeCodeCase, ...],
    behaviors: tuple[BehavioralCase, ...],
) -> None:
    events: list[str] = []
    snapshot = bound_module._snapshot

    def capture(*args: Any) -> dict[str, object]:
        events.append("snapshot")
        return snapshot(*args)

    provider = _FullProvider(nodes)
    complete = provider.complete

    def generate(request: NodeCodeRequest) -> str:
        events.append("provider")
        return complete(request)

    monkeypatch.setattr(bound_module, "_snapshot", capture)
    monkeypatch.setattr(provider, "complete", generate)
    _workers(monkeypatch, behaviors)
    run_corpus_bound_code_benchmark(
        behaviors, nodes, provider, allow_untrusted_code_execution=True, project_root=ROOT
    )
    assert events == ["snapshot", *["provider"] * len(nodes)]

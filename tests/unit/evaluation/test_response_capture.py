from __future__ import annotations

import ast
import json
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from notebook_to_kedro import cli
from notebook_to_kedro.evaluation import (
    BehavioralBenchmarkConfiguration,
    BehavioralBenchmarkProvenance,
    BehavioralCase,
    BehavioralExecutionException,
    BehavioralExecutionOutput,
    BehavioralExecutionResult,
    CorpusBoundCodeBenchmarkReport,
    NodeBodyBenchmarkReport,
    NodeCodeCase,
    ResponseCaptureProvider,
    behavioral_proposal,
    create_response_capture,
    load_behavioral_benchmark_artifact,
    load_behavioral_corpus,
    load_corpus_bound_code_artifact,
    load_node_body_benchmark_artifact,
    load_node_code_corpus,
    load_response_capture,
    recover_response_capture,
    response_capture_summary,
    run_behavioral_code_benchmark,
    write_json_exclusive,
)
from notebook_to_kedro.evaluation import response_capture as capture_module
from notebook_to_kedro.evaluation.behavioral_artifacts import _json_sha256
from notebook_to_kedro.exceptions import BehavioralBenchmarkArtifactError, NodeCodeProviderError
from notebook_to_kedro.generation.code import NodeBodyResponse, NodeCodeRequest, NodeCodeResponse

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = Path(__file__).parents[3]
PROVENANCE = BehavioralBenchmarkProvenance(
    "2026-10-11T09:00:00Z", "revision", "3.12.14", "win32", "0.40.2", "a" * 64
)
BEHAVIORS = ROOT / "tests/fixtures/evaluation/behavioral/v3"
NODES = ROOT / "tests/fixtures/evaluation/node_code/v3"
Corpus = tuple[tuple[BehavioralCase, ...], tuple[NodeCodeCase, ...]]


class _Provider:
    provider_name = "offline-reference"
    model_name = "fixed"

    def __init__(self, nodes: tuple[NodeCodeCase, ...], *, body: bool = False) -> None:
        self.prompt_version = "node-body-v1" if body else "node-code-v4"
        self.calls: list[NodeCodeRequest] = []
        self.responses: dict[str, str | Exception] = {}
        for node in nodes:
            if body:
                function = ast.parse(node.reference_response.function_code).body[0]
                assert isinstance(function, ast.FunctionDef)
                body_code = ast.unparse(ast.Module(body=function.body[:-1], type_ignores=[]))
                raw = NodeBodyResponse(
                    "1.0", node.request.request_id, node.request.task_id, body_code
                ).to_json()
            else:
                raw = node.reference_response.to_json()
            self.responses[node.request.request_id] = " \n" + raw + "\n\t"

    def complete(self, request: NodeCodeRequest) -> str:
        self.calls.append(request)
        value = self.responses[request.request_id]
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def corpus() -> Corpus:
    return load_behavioral_corpus(BEHAVIORS), load_node_code_corpus(NODES)


def _new(
    tmp_path: Path, corpus: Corpus, **options: Any
) -> tuple[ResponseCaptureProvider, _Provider]:
    behaviors, nodes = corpus
    proposal_format = options.pop("proposal_format", "full-code")
    provider = options.pop("provider", _Provider(nodes, body=proposal_format == "node-body"))
    defaults = {
        "provenance": PROVENANCE,
        "configuration": BehavioralBenchmarkConfiguration(
            "http://localhost:11434", 120, include_parameter_evidence=True
        ),
        "prompt_version": provider.prompt_version,
        "proposal_format": proposal_format,
        "allow_untrusted_code_execution": True,
        "project_root": ROOT,
    }
    defaults.update(options)
    return create_response_capture(
        tmp_path / "capture", behaviors, nodes, provider, **defaults
    ), provider


def _publish(adapter: ResponseCaptureProvider, corpus: Corpus) -> None:
    for node in corpus[1]:
        with suppress(NodeCodeProviderError):
            adapter.complete(node.request)


def _executions(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def execute(
        case: BehavioralCase, *_args: object, **_kwargs: object
    ) -> BehavioralExecutionResult:
        calls.append(case.case_id)
        expected = case.expected_exception
        return BehavioralExecutionResult(
            "1.0",
            case.case_id,
            case.node_code_case_id,
            "exception" if expected else "success",
            tuple(
                BehavioralExecutionOutput(output.output_name, output.value)
                for output in case.expected_outputs
            ),
            (
                BehavioralExecutionException(
                    expected.type_name, expected.message_contains or "expected"
                )
                if expected
                else None
            ),
            "",
            "",
            stdout_truncated=False,
            stderr_truncated=False,
            duration_seconds=0.1,
        )

    monkeypatch.setattr(behavioral_proposal, "execute_behavioral_proposal", execute)
    return calls


@pytest.mark.parametrize("proposal_format", ["full-code", "bound-full-code", "node-body"])
def test_complete_capture_recovers_exact_raw_outcomes_offline(
    tmp_path: Path,
    corpus: Corpus,
    monkeypatch: pytest.MonkeyPatch,
    proposal_format: str,
) -> None:
    adapter, provider = _new(tmp_path, corpus, proposal_format=proposal_format)
    error_node = corpus[1][-1]
    provider.responses[error_node.request.request_id] = NodeCodeProviderError(
        "transport", "offline"
    )
    _publish(adapter, corpus)
    capture = load_response_capture(tmp_path / "capture")
    summary = response_capture_summary(capture)
    assert summary["complete"] is True
    assert summary["benchmark_completed"] is False
    assert summary["provider_error_count"] == 1
    assert summary["recorded_outcome_count"] == 4
    assert capture.configuration.execution.timeout_seconds == 10
    assert len(provider.calls) == 4
    raw = {row["request_sha256"]: row["raw_response"] for row in capture.responses}
    for node in corpus[1][:-1]:
        assert (
            raw[capture_module._request_sha256(node.request)]
            == provider.responses[node.request.request_id]
        )
    monkeypatch.setattr(provider, "complete", lambda _request: pytest.fail("live provider called"))
    calls = _executions(monkeypatch)
    report = recover_response_capture(
        capture, *corpus, allow_untrusted_code_execution=True, project_root=ROOT
    )
    benchmark = (
        report.benchmark
        if isinstance(report, (NodeBodyBenchmarkReport, CorpusBoundCodeBenchmarkReport))
        else report
    )
    assert benchmark.provider_name == "offline-reference"
    assert benchmark.model_name == "fixed"
    assert benchmark.scenario_count == 12
    assert len(calls) == 9
    assert all(proposal.proposal_duration_seconds == 0 for proposal in benchmark.proposals)
    assert benchmark.proposals[-1].status == "provider_error"
    assert benchmark.proposals[-1].diagnostic_code == "transport"
    assert benchmark.proposals[-1].diagnostic_message == "offline"


def test_partial_capture_is_inspectable_and_cannot_be_scored(
    tmp_path: Path, corpus: Corpus
) -> None:
    adapter, provider = _new(tmp_path, corpus)
    node = corpus[1][0]
    provider.responses[node.request.request_id] = "not JSON \N{LATIN SMALL LETTER E WITH ACUTE}"
    assert adapter.complete(node.request) == provider.responses[node.request.request_id]
    capture = load_response_capture(tmp_path / "capture")
    summary = response_capture_summary(capture)
    assert summary["complete"] is False
    assert summary["missing_node_code_case_ids"] == [node.case_id for node in corpus[1][1:]]
    with pytest.raises(ValueError, match="incomplete"):
        recover_response_capture(capture, *corpus, allow_untrusted_code_execution=True)
    with pytest.raises(BehavioralBenchmarkArtifactError, match="already exists"):
        adapter.complete(node.request)
    assert len(provider.calls) == 1
    with pytest.raises(BehavioralBenchmarkArtifactError, match="new capture"):
        _new(tmp_path, corpus)


def test_capture_survives_execution_interruption(
    tmp_path: Path,
    corpus: Corpus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, provider = _new(tmp_path, corpus)

    def fail_execution(*_args: object, **_kwargs: object) -> BehavioralExecutionResult:
        captured = load_response_capture(tmp_path / "capture")
        assert len(captured.responses) == 1
        assert (
            captured.responses[0]["raw_response"]
            == provider.responses[corpus[1][0].request.request_id]
        )
        raise RuntimeError("execution interrupted")

    monkeypatch.setattr(behavioral_proposal, "execute_behavioral_proposal", fail_execution)
    with pytest.raises(RuntimeError, match="execution interrupted"):
        run_behavioral_code_benchmark(
            *corpus, adapter, allow_untrusted_code_execution=True, project_root=ROOT
        )
    assert len(provider.calls) == 1
    assert len(load_response_capture(tmp_path / "capture").responses) == 1


def test_response_write_failure_prevents_validation_and_retry(
    tmp_path: Path,
    corpus: Corpus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, provider = _new(tmp_path, corpus)

    def fail_response(path: str | Path, payload: Any) -> None:
        if Path(path).parent.name == "responses":
            raise BehavioralBenchmarkArtifactError("disk full")
        write_json_exclusive(path, payload)

    monkeypatch.setattr(capture_module, "write_json_exclusive", fail_response)
    monkeypatch.setattr(
        NodeCodeResponse, "from_json", lambda *_args, **_kwargs: pytest.fail("validation ran")
    )
    with pytest.raises(BehavioralBenchmarkArtifactError, match="disk full"):
        adapter.complete(corpus[1][0].request)
    assert len(provider.calls) == 1
    assert not list((tmp_path / "capture/responses").glob("*.json"))
    with pytest.raises(BehavioralBenchmarkArtifactError, match="already exists"):
        adapter.complete(corpus[1][0].request)
    assert len(provider.calls) == 1


def test_capture_preflight_consent_and_request_identity(tmp_path: Path, corpus: Corpus) -> None:
    with pytest.raises(ValueError, match="allow_untrusted"):
        _new(tmp_path, corpus, allow_untrusted_code_execution=False)
    assert not (tmp_path / "capture").exists()
    bad_nodes = (replace(corpus[1][0], source_sha256="0" * 64), *corpus[1][1:])
    with pytest.raises(ValueError, match=r"hash|SHA|source"):
        _new(tmp_path, (corpus[0], bad_nodes))
    adapter, provider = _new(tmp_path, corpus)
    with pytest.raises(BehavioralBenchmarkArtifactError, match="exact corpus"):
        adapter.complete(replace(corpus[1][0].request, node_name="different"))
    assert not provider.calls
    capture = load_response_capture(tmp_path / "capture")
    with pytest.raises(ValueError, match="allow_untrusted"):
        recover_response_capture(capture, *corpus)
    with pytest.raises(ValueError, match="exact complete corpus"):
        recover_response_capture(
            capture, corpus[0][1:], corpus[1], allow_untrusted_code_execution=True
        )


@pytest.mark.parametrize("failure", [RuntimeError("unexpected provider failure"), 1])
def test_unexpected_provider_failure_leaves_reserved_missing_outcome(
    tmp_path: Path,
    corpus: Corpus,
    failure: Any,
) -> None:
    adapter, provider = _new(tmp_path, corpus)
    provider.responses[corpus[1][0].request.request_id] = failure
    with pytest.raises((RuntimeError, BehavioralBenchmarkArtifactError), match=r"failure|string"):
        adapter.complete(corpus[1][0].request)
    assert len(provider.calls) == 1
    assert load_response_capture(tmp_path / "capture").missing_node_code_case_ids == tuple(
        node.case_id for node in corpus[1]
    )


@pytest.mark.parametrize("proposal_format", ["full-code", "bound-full-code", "node-body"])
def test_cli_capture_and_recovery_keep_existing_artifact_formats(
    tmp_path: Path,
    corpus: Corpus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    proposal_format: str,
) -> None:
    provider = _Provider(corpus[1], body=proposal_format == "node-body")
    provider_class = (
        "OllamaNodeBodyProvider" if proposal_format == "node-body" else "OllamaNodeCodeProvider"
    )
    monkeypatch.setattr(cli, provider_class, lambda *_args, **_kwargs: provider)
    metadata_calls: list[dict[str, Any]] = []

    def provenance(**kwargs: Any) -> BehavioralBenchmarkProvenance:
        metadata_calls.append(kwargs)
        return PROVENANCE

    monkeypatch.setattr(cli, "collect_environment_provenance", provenance)
    calls = _executions(monkeypatch)
    live = tmp_path / "live.json"
    assert (
        cli.main(
            [
                "behavioral-benchmark",
                "run",
                str(BEHAVIORS),
                str(NODES),
                str(live),
                "--ollama-model",
                "fixed",
                "--proposal-format",
                proposal_format,
                "--project-root",
                str(ROOT),
                "--capture-dir",
                str(tmp_path / "capture"),
                "--allow-untrusted-code-execution",
            ]
        )
        == 0
    )
    assert len(provider.calls) == 4
    assert len(metadata_calls) == 1
    assert len(calls) == 12
    assert cli.main(["behavioral-benchmark", "capture-info", str(tmp_path / "capture")]) == 0
    assert '"benchmark_completed": false' in capsys.readouterr().out
    calls.clear()
    recovered = tmp_path / "recovered.json"
    assert (
        cli.main(
            [
                "behavioral-benchmark",
                "recover",
                str(tmp_path / "capture"),
                str(BEHAVIORS),
                str(NODES),
                str(recovered),
                "--project-root",
                str(ROOT),
                "--allow-untrusted-code-execution",
            ]
        )
        == 0
    )
    assert len(provider.calls) == 4
    assert len(calls) == 12
    assert metadata_calls[-1] == {"project_root": ROOT}
    if proposal_format == "node-body":
        artifact = load_node_body_benchmark_artifact(recovered).benchmark
    elif proposal_format == "bound-full-code":
        artifact = load_corpus_bound_code_artifact(recovered).benchmark
    else:
        artifact = load_behavioral_benchmark_artifact(recovered)
    assert artifact.mode == "replay"
    assert (
        artifact.source_artifact_sha256
        == load_response_capture(tmp_path / "capture").capture_sha256
    )
    assert "Created recovered benchmark artifact" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "2.0"),
        ("artifact_kind", "scored-benchmark"),
        ("proposal_format", "other"),
        ("validator_version", "old"),
        ("execution_policy", "unrestricted"),
        ("provider_name", ""),
        ("model_name", ""),
        ("prompt_version", " "),
        ("corpus_sha256", "0" * 64),
        ("extra", True),
    ],
)
def test_manifest_rejects_unsupported_or_mutated_evidence(
    tmp_path: Path,
    corpus: Corpus,
    field: str,
    value: object,
) -> None:
    _new(tmp_path, corpus)
    path = tmp_path / "capture/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest[field] = value
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BehavioralBenchmarkArtifactError):
        load_response_capture(tmp_path / "capture")


def test_creation_rejects_invalid_format_body_evidence_and_empty_prompt(
    tmp_path: Path,
    corpus: Corpus,
) -> None:
    for options in (
        {"proposal_format": "other"},
        {"prompt_version": ""},
        {
            "proposal_format": "node-body",
            "configuration": BehavioralBenchmarkConfiguration(
                "http://localhost:11434", 120, include_parameter_evidence=False
            ),
        },
    ):
        with pytest.raises(ValueError, match=r"capture|body"):
            _new(tmp_path, corpus, **options)
        assert not (tmp_path / "capture").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "2.0"),
        ("artifact_kind", "scored-benchmark"),
        ("manifest_sha256", "0" * 64),
        ("request_sha256", "0" * 64),
        ("raw_response", "changed"),
        ("raw_response_sha256", "0" * 64),
        ("diagnostic_code", "unexpected"),
        ("diagnostic_message", "unexpected"),
        ("status", "accepted"),
        ("extra", True),
    ],
)
def test_response_files_reject_tampering(
    tmp_path: Path,
    corpus: Corpus,
    field: str,
    value: object,
) -> None:
    adapter, _ = _new(tmp_path, corpus)
    adapter.complete(corpus[1][0].request)
    path = next((tmp_path / "capture/responses").glob("*.json"))
    record = json.loads(path.read_text(encoding="utf-8"))
    record[field] = value
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(BehavioralBenchmarkArtifactError):
        load_response_capture(tmp_path / "capture")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("raw_response", "unexpected"),
        ("raw_response_sha256", "0" * 64),
        ("diagnostic_code", ""),
        ("diagnostic_message", ""),
    ],
)
def test_provider_failure_must_preserve_only_its_diagnostic(
    tmp_path: Path,
    corpus: Corpus,
    field: str,
    value: object,
) -> None:
    adapter, provider = _new(tmp_path, corpus)
    provider.responses[corpus[1][0].request.request_id] = NodeCodeProviderError("error", "failed")
    with pytest.raises(NodeCodeProviderError):
        adapter.complete(corpus[1][0].request)
    path = next((tmp_path / "capture/responses").glob("*.json"))
    record = json.loads(path.read_text(encoding="utf-8"))
    record[field] = value
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(BehavioralBenchmarkArtifactError):
        load_response_capture(tmp_path / "capture")


@pytest.mark.parametrize(
    "failure", ["attempt", "filename", "unreserved", "json", "duplicate_json", "missing"]
)
def test_loader_rejects_invalid_file_bindings_and_json(
    tmp_path: Path,
    corpus: Corpus,
    failure: str,
) -> None:
    adapter, _ = _new(tmp_path, corpus)
    adapter.complete(corpus[1][0].request)
    root = tmp_path / "capture"
    attempt = next((root / "attempts").glob("*.json"))
    if failure == "attempt":
        attempt.write_text(
            json.dumps({"manifest_sha256": "bad", "request_sha256": attempt.stem}), encoding="utf-8"
        )
    elif failure == "filename":
        attempt.rename(attempt.with_name("unknown.json"))
    elif failure == "unreserved":
        attempt.unlink()
    elif failure == "missing":
        (root / "manifest.json").unlink()
    else:
        (root / "manifest.json").write_text(
            '{"schema_version":"1.0","schema_version":"1.0"}'
            if failure == "duplicate_json"
            else "not JSON",
            encoding="utf-8",
        )
    with pytest.raises(BehavioralBenchmarkArtifactError):
        load_response_capture(root)


@pytest.mark.parametrize("mutation", ["manifest", "digest", "duplicate", "unknown", "missing_key"])
def test_in_memory_capture_is_revalidated_before_recovery(
    tmp_path: Path,
    corpus: Corpus,
    mutation: str,
) -> None:
    adapter, _ = _new(tmp_path, corpus)
    _publish(adapter, corpus)
    capture = load_response_capture(tmp_path / "capture")
    if mutation == "manifest":
        capture = replace(capture, manifest_sha256="0" * 64)
    elif mutation == "digest":
        capture = replace(capture, capture_sha256="0" * 64)
    else:
        rows = capture.responses
        if mutation == "duplicate":
            rows = (*rows, rows[0])
        elif mutation == "unknown":
            rows[0]["request_sha256"] = "0" * 64
        else:
            del rows[0]["request_sha256"]
            with pytest.raises(ValueError, match="request_sha256"):
                recover_response_capture(capture, *corpus, allow_untrusted_code_execution=True)
            return
        capture = replace(
            capture,
            responses=rows,
            capture_sha256=capture_module._capture_sha256(capture.manifest, rows),
        )
    with pytest.raises(ValueError, match="capture"):
        recover_response_capture(capture, *corpus, allow_untrusted_code_execution=True)


def test_complete_invalid_raw_capture_is_revalidated_without_execution(
    tmp_path: Path,
    corpus: Corpus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, provider = _new(tmp_path, corpus)
    for node in corpus[1]:
        provider.responses[node.request.request_id] = "not JSON"
    _publish(adapter, corpus)
    calls = _executions(monkeypatch)
    report = recover_response_capture(
        load_response_capture(tmp_path / "capture"),
        *corpus,
        allow_untrusted_code_execution=True,
        project_root=ROOT,
    )
    assert not isinstance(report, (NodeBodyBenchmarkReport, CorpusBoundCodeBenchmarkReport))
    assert all(proposal.status == "invalid_response" for proposal in report.proposals)
    assert not calls
    assert report.scenario_count == 12


def test_complete_capture_survives_last_node_execution_failure(
    tmp_path: Path,
    corpus: Corpus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, provider = _new(tmp_path, corpus)
    calls = _executions(monkeypatch)
    execute = cast(
        "Callable[..., BehavioralExecutionResult]",
        vars(behavioral_proposal)["execute_behavioral_proposal"],
    )

    def interrupted(case: BehavioralCase, *args: Any, **kwargs: Any) -> BehavioralExecutionResult:
        if case.node_code_case_id == corpus[1][-1].case_id:
            raise RuntimeError("last node interrupted")
        return execute(case, *args, **kwargs)

    monkeypatch.setattr(behavioral_proposal, "execute_behavioral_proposal", interrupted)
    with pytest.raises(RuntimeError, match="last node interrupted"):
        run_behavioral_code_benchmark(
            *corpus, adapter, allow_untrusted_code_execution=True, project_root=ROOT
        )
    capture = load_response_capture(tmp_path / "capture")
    assert not capture.missing_node_code_case_ids
    assert len(provider.calls) == 4
    monkeypatch.setattr(behavioral_proposal, "execute_behavioral_proposal", execute)
    calls.clear()
    recover_response_capture(
        capture, *corpus, allow_untrusted_code_execution=True, project_root=ROOT
    )
    assert len(calls) == 12
    assert len(provider.calls) == 4


@pytest.mark.parametrize("mutation", ["empty", "duplicate_request"])
def test_manifest_rejects_empty_corpus_and_duplicate_request_ids(
    tmp_path: Path,
    corpus: Corpus,
    mutation: str,
) -> None:
    _new(tmp_path, corpus)
    path = tmp_path / "capture/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "empty":
        manifest["corpus"] = {"behaviors": [], "nodes": []}
    else:
        nodes = manifest["corpus"]["nodes"]
        case_id = nodes[1]["case_id"]
        nodes[1] = json.loads(json.dumps(nodes[0]))
        nodes[1]["case_id"] = case_id
    manifest["corpus_sha256"] = _json_sha256(manifest["corpus"])
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(BehavioralBenchmarkArtifactError, match=r"unique request|nonempty"):
        load_response_capture(tmp_path / "capture")

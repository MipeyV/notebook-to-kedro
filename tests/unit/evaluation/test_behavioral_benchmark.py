from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from math import inf, nan
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

from notebook_to_kedro.evaluation import (
    BEHAVIORAL_CODE_BENCHMARK_SCHEMA_VERSION,
    BEHAVIORAL_PROPOSAL_EXECUTION_POLICY,
    BehavioralCase,
    NodeCodeCase,
    ScalarBehaviorValue,
    behavior_value_to_dict,
    behavioral_code_benchmark_to_dict,
    behavioral_code_benchmark_to_json,
    load_behavioral_corpus,
    load_node_code_corpus,
    run_behavioral_code_benchmark,
)
from notebook_to_kedro.evaluation import behavioral_benchmark as benchmark
from notebook_to_kedro.exceptions import NodeCodeProviderError
from notebook_to_kedro.generation.code import (
    NODE_CODE_VALIDATOR_VERSION,
    NodeCodeRequest,
    NodeCodeResponse,
)

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = Path(__file__).parents[3]
BEHAVIOR_DIRECTORY = ROOT / "tests/fixtures/evaluation/behavioral/v1"
NODE_DIRECTORY = ROOT / "tests/fixtures/evaluation/node_code/v1"


class _FakeProcess:
    pid = 123

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        return 0

    def kill(self) -> None:
        return None


class _CorpusProvider:
    provider_name = "fake-corpus"
    model_name = "reviewed-responses"

    def __init__(
        self,
        nodes: tuple[NodeCodeCase, ...],
        mutate: Callable[[int, NodeCodeRequest, NodeCodeResponse], str] | None = None,
    ) -> None:
        self.requests: list[NodeCodeRequest] = []
        self.responses = {node.request.request_id: node.reference_response for node in nodes}
        self.mutate = mutate

    def complete(self, request: NodeCodeRequest) -> str:
        self.requests.append(request)
        response = self.responses[request.request_id]
        if self.mutate is not None:
            return self.mutate(len(self.requests), request, response)
        return response.to_json()


@pytest.fixture
def behaviors() -> tuple[BehavioralCase, ...]:
    return load_behavioral_corpus(BEHAVIOR_DIRECTORY)


@pytest.fixture
def nodes() -> tuple[NodeCodeCase, ...]:
    return load_node_code_corpus(NODE_DIRECTORY)


def _worker_result(
    case: BehavioralCase,
    *,
    status: str | None = None,
    value: object | None = None,
) -> dict[str, object]:
    if status is not None:
        return {
            "schema_version": "1.0",
            "case_id": case.case_id,
            "node_code_case_id": case.node_code_case_id,
            "status": status,
            "outputs": [],
            "exception": None,
            "stdout": "",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "diagnostic_message": f"{status} diagnostic",
        }
    if case.expected_exception is not None:
        expected = case.expected_exception
        return {
            "schema_version": "1.0",
            "case_id": case.case_id,
            "node_code_case_id": case.node_code_case_id,
            "status": "exception",
            "outputs": [],
            "exception": {
                "type_name": expected.type_name,
                "message": expected.message_contains or "expected exception",
            },
            "stdout": "",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "diagnostic_message": None,
        }
    outputs = [
        {
            "output_name": expected.output_name,
            "value": behavior_value_to_dict(
                expected.value if value is None or index > 0 else cast("Any", value)
            ),
        }
        for index, expected in enumerate(case.expected_outputs)
    ]
    return {
        "schema_version": "1.0",
        "case_id": case.case_id,
        "node_code_case_id": case.node_code_case_id,
        "status": "success",
        "outputs": outputs,
        "exception": None,
        "stdout": "",
        "stderr": "",
        "stdout_truncated": False,
        "stderr_truncated": False,
        "diagnostic_message": None,
    }


def _install_workers(
    monkeypatch: pytest.MonkeyPatch,
    behaviors: tuple[BehavioralCase, ...],
    overrides: dict[str, dict[str, object]] | None = None,
) -> None:
    by_id = {case.case_id: case for case in behaviors}

    def fake_popen(command: tuple[str, ...], **_kwargs: object) -> subprocess.Popen[bytes]:
        request = json.loads(Path(command[-3]).read_text(encoding="utf-8"))
        case = by_id[request["case_id"]]
        options = (overrides or {}).get(case.case_id, {})
        Path(command[-2]).write_text(
            json.dumps(_worker_result(case, **cast("Any", options))),
            encoding="utf-8",
        )
        return cast("subprocess.Popen[bytes]", _FakeProcess())

    monkeypatch.setattr(subprocess, "Popen", fake_popen)


def test_benchmark_measures_static_and_behavioral_success(
    monkeypatch: pytest.MonkeyPatch,
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
) -> None:
    provider = _CorpusProvider(nodes)
    _install_workers(monkeypatch, behaviors)
    ticks = iter(float(value) / 2 for value in range(8))

    report = run_behavioral_code_benchmark(
        behaviors,
        nodes,
        provider,
        allow_untrusted_code_execution=True,
        project_root=ROOT,
        prompt_version="test-prompt",
        clock=lambda: next(ticks),
    )
    payload = behavioral_code_benchmark_to_dict(report)
    summary = cast("dict[str, object]", payload["summary"])

    assert report.schema_version == BEHAVIORAL_CODE_BENCHMARK_SCHEMA_VERSION
    assert report.validator_version == NODE_CODE_VALIDATOR_VERSION
    assert report.execution_policy == BEHAVIORAL_PROPOSAL_EXECUTION_POLICY
    assert (report.provider_name, report.model_name, report.prompt_version) == (
        "fake-corpus",
        "reviewed-responses",
        "test-prompt",
    )
    assert len(report.proposals) == len(provider.requests) == 4
    assert all(proposal.status == "accepted" for proposal in report.proposals)
    assert sum(len(proposal.evaluations) for proposal in report.proposals) == 5
    assert summary["accepted_rate"] == 1.0
    assert summary["evaluated_scenario_count"] == summary["matched_scenario_count"] == 5
    assert summary["evaluated_match_rate"] == summary["end_to_end_match_rate"] == 1.0
    assert summary["provider_duration_seconds"] == 2.0
    assert summary["mean_provider_duration_seconds"] == 0.5
    assert cast("float", summary["execution_duration_seconds"]) >= 0
    assert json.loads(behavioral_code_benchmark_to_json(report)) == payload
    assert json.loads(behavioral_code_benchmark_to_json(report, indent=None)) == payload


def test_benchmark_records_provider_response_and_static_failures(
    monkeypatch: pytest.MonkeyPatch,
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
) -> None:
    def mutate(index: int, _request: NodeCodeRequest, response: NodeCodeResponse) -> str:
        if index == 1:
            raise NodeCodeProviderError("ollama_timeout", "timed out")
        if index == 2:
            return "not-json"
        if index == 3:
            return replace(response, request_id="wrong-request").to_json()
        return response.to_json()

    provider = _CorpusProvider(nodes, mutate)
    _install_workers(monkeypatch, behaviors)
    report = run_behavioral_code_benchmark(
        behaviors,
        nodes,
        provider,
        allow_untrusted_code_execution=True,
        project_root=ROOT,
    )
    summary = cast("dict[str, object]", behavioral_code_benchmark_to_dict(report)["summary"])

    assert tuple(proposal.status for proposal in report.proposals) == (
        "provider_error",
        "invalid_response",
        "invalid_code",
        "accepted",
    )
    assert report.proposals[0].diagnostic_code == "ollama_timeout"
    assert report.proposals[0].raw_response is None
    assert report.proposals[1].raw_response == "not-json"
    assert report.proposals[1].response is None
    assert report.proposals[2].response is not None
    assert summary["accepted_count"] == 1
    assert summary["provider_error_count"] == 1
    assert summary["invalid_response_count"] == 1
    assert summary["invalid_code_count"] == 1
    assert summary["evaluated_scenario_count"] == summary["matched_scenario_count"] == 1
    assert summary["not_evaluated_scenario_count"] == 4
    assert summary["evaluated_match_rate"] == 1.0
    assert summary["end_to_end_match_rate"] == 0.2


def test_benchmark_distinguishes_mismatch_and_execution_error(
    monkeypatch: pytest.MonkeyPatch,
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
) -> None:
    _install_workers(
        monkeypatch,
        behaviors,
        {
            "evaluate-regression-standard": {"value": ScalarBehaviorValue(99.0)},
            "fill-missing-standard": {"status": "serialization_failure"},
        },
    )
    report = run_behavioral_code_benchmark(
        behaviors,
        nodes,
        _CorpusProvider(nodes),
        allow_untrusted_code_execution=True,
        project_root=ROOT,
    )
    summary = cast("dict[str, object]", behavioral_code_benchmark_to_dict(report)["summary"])

    assert summary["matched_scenario_count"] == 3
    assert summary["mismatch_scenario_count"] == 1
    assert summary["execution_error_scenario_count"] == 1
    assert summary["evaluated_match_rate"] == summary["end_to_end_match_rate"] == 0.6


def test_benchmark_preflight_and_consent_fail_before_provider_calls(
    behaviors: tuple[BehavioralCase, ...], nodes: tuple[NodeCodeCase, ...]
) -> None:
    provider = _CorpusProvider(nodes)

    for consent in (False, cast("Any", 1), cast("Any", "yes")):
        with pytest.raises(ValueError, match="allow_untrusted_code_execution=True"):
            run_behavioral_code_benchmark(
                behaviors,
                nodes,
                provider,
                allow_untrusted_code_execution=consent,
                project_root=ROOT,
            )
    with pytest.raises(ValueError, match="at least one"):
        run_behavioral_code_benchmark(
            (), nodes, provider, allow_untrusted_code_execution=True, project_root=ROOT
        )
    with pytest.raises(ValueError, match="scenarios for every"):
        run_behavioral_code_benchmark(
            behaviors[:-1],
            nodes,
            provider,
            allow_untrusted_code_execution=True,
            project_root=ROOT,
        )
    with pytest.raises(ValueError, match="source hash"):
        run_behavioral_code_benchmark(
            behaviors,
            (replace(nodes[0], source_sha256="0" * 64), *nodes[1:]),
            provider,
            allow_untrusted_code_execution=True,
            project_root=ROOT,
        )
    invalid_reference = replace(nodes[0], reference_response=nodes[0].invalid_examples[0].response)
    with pytest.raises(ValueError, match="Invalid node code"):
        run_behavioral_code_benchmark(
            behaviors,
            (invalid_reference, *nodes[1:]),
            provider,
            allow_untrusted_code_execution=True,
            project_root=ROOT,
        )
    assert not provider.requests


@pytest.mark.parametrize("ticks", [(1.0, 0.0), (0.0, nan), (0.0, inf)])
def test_benchmark_rejects_invalid_clock(
    monkeypatch: pytest.MonkeyPatch,
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
    ticks: tuple[float, float],
) -> None:
    _install_workers(monkeypatch, behaviors)
    values = iter(ticks)
    with pytest.raises(ValueError, match="non-negative finite duration"):
        run_behavioral_code_benchmark(
            behaviors,
            nodes,
            _CorpusProvider(nodes),
            allow_untrusted_code_execution=True,
            project_root=ROOT,
            clock=lambda: next(values),
        )


def test_benchmark_propagates_unexpected_provider_bugs(
    behaviors: tuple[BehavioralCase, ...], nodes: tuple[NodeCodeCase, ...]
) -> None:
    def mutate(_index: int, _request: NodeCodeRequest, _response: NodeCodeResponse) -> str:
        raise RuntimeError("provider implementation bug")

    with pytest.raises(RuntimeError, match="implementation bug"):
        run_behavioral_code_benchmark(
            behaviors,
            nodes,
            _CorpusProvider(nodes, mutate),
            allow_untrusted_code_execution=True,
            project_root=ROOT,
        )


def test_empty_serialized_report_has_defined_rates(
    monkeypatch: pytest.MonkeyPatch,
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
) -> None:
    _install_workers(monkeypatch, behaviors)
    report = run_behavioral_code_benchmark(
        behaviors,
        nodes,
        _CorpusProvider(nodes),
        allow_untrusted_code_execution=True,
        project_root=ROOT,
    )
    empty = replace(report, scenario_count=0, proposals=())
    summary = cast("dict[str, object]", behavioral_code_benchmark_to_dict(empty)["summary"])

    assert summary["accepted_rate"] == 0.0
    assert summary["evaluated_match_rate"] == 0.0
    assert summary["end_to_end_match_rate"] == 0.0
    assert summary["mean_provider_duration_seconds"] == 0.0


def test_accepted_internal_proposal_requires_a_response(
    monkeypatch: pytest.MonkeyPatch,
    behaviors: tuple[BehavioralCase, ...],
    nodes: tuple[NodeCodeCase, ...],
) -> None:
    monkeypatch.setattr(
        benchmark,
        "_request_proposal",
        lambda proposal, _provider: proposal,
    )
    ticks = iter((0.0, 1.0))
    with pytest.raises(ValueError, match="must contain"):
        benchmark._run_proposal(
            nodes[0],
            (behaviors[0],),
            _CorpusProvider(nodes),
            None,
            lambda: next(ticks),
        )

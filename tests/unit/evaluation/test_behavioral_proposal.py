from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from notebook_to_kedro.evaluation import (
    BEHAVIORAL_PROPOSAL_EVALUATION_SCHEMA_VERSION,
    BehavioralCase,
    BehavioralCaseComparison,
    BehavioralExecutionException,
    BehavioralExecutionResult,
    BehavioralProposalEvaluation,
    NodeCodeCase,
    ScalarBehaviorValue,
    behavior_value_to_dict,
    behavioral_proposal_evaluation_to_dict,
    behavioral_proposal_evaluation_to_json,
    evaluate_behavioral_proposal,
    execute_behavioral_proposal,
    load_behavioral_corpus,
    load_node_code_corpus,
)
from notebook_to_kedro.evaluation import behavioral_execution as execution

BEHAVIOR_DIRECTORY = Path("tests/fixtures/evaluation/behavioral/v1")
NODE_DIRECTORY = Path("tests/fixtures/evaluation/node_code/v1")


class _FakeProcess:
    def __init__(self, return_code: int = 0, *, timeout: bool = False) -> None:
        self.pid = 123
        self.return_code = return_code
        self.timeout = timeout

    def wait(self, timeout: float | None = None) -> int:
        if self.timeout:
            raise subprocess.TimeoutExpired("worker", timeout or 0.0)
        return self.return_code

    def kill(self) -> None:
        return None


def _reviewed_pair(
    case_id: str = "evaluate-regression-standard",
) -> tuple[BehavioralCase, NodeCodeCase]:
    behaviors = {case.case_id: case for case in load_behavioral_corpus(BEHAVIOR_DIRECTORY)}
    nodes = {case.case_id: case for case in load_node_code_corpus(NODE_DIRECTORY)}
    case = behaviors[case_id]
    return case, nodes[case.node_code_case_id]


def _worker_result(
    case: BehavioralCase,
    *,
    status: str = "success",
    value: object | None = None,
    exception: dict[str, str] | None = None,
    diagnostic: str | None = None,
) -> dict[str, object]:
    outputs: list[object] = []
    if status == "success":
        expected = case.expected_outputs[0]
        outputs = [
            {
                "output_name": expected.output_name,
                "value": behavior_value_to_dict(
                    expected.value if value is None else cast("Any", value)
                ),
            }
        ]
    return {
        "schema_version": "1.0",
        "case_id": case.case_id,
        "node_code_case_id": case.node_code_case_id,
        "status": status,
        "outputs": outputs,
        "exception": exception,
        "stdout": "",
        "stderr": "",
        "stdout_truncated": False,
        "stderr_truncated": False,
        "diagnostic_message": diagnostic,
    }


def _install_worker_result(monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]) -> None:
    def fake_popen(command: tuple[str, ...], **_kwargs: object) -> subprocess.Popen[bytes]:
        Path(command[-2]).write_text(json.dumps(payload), encoding="utf-8")
        return cast("subprocess.Popen[bytes]", _FakeProcess())

    monkeypatch.setattr(subprocess, "Popen", fake_popen)


def test_proposal_evaluation_executes_compares_hashes_and_serializes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, node = _reviewed_pair()
    _install_worker_result(monkeypatch, _worker_result(case))

    evaluation = evaluate_behavioral_proposal(
        case,
        node,
        node.reference_response,
        allow_untrusted_code_execution=True,
    )
    payload = behavioral_proposal_evaluation_to_dict(evaluation)
    execution_payload = cast("dict[str, object]", payload["execution"])
    comparison_payload = cast("dict[str, object]", payload["comparison"])

    assert evaluation.schema_version == BEHAVIORAL_PROPOSAL_EVALUATION_SCHEMA_VERSION
    assert evaluation.matched
    assert len(evaluation.response_sha256) == 64
    assert execution_payload["status"] == "success"
    assert comparison_payload["status"] == "matched"
    assert json.loads(behavioral_proposal_evaluation_to_json(evaluation)) == payload


def test_proposal_evaluation_reports_output_and_exception_mismatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, node = _reviewed_pair()
    _install_worker_result(monkeypatch, _worker_result(case, value=ScalarBehaviorValue(99.0)))
    output_mismatch = evaluate_behavioral_proposal(
        case,
        node,
        node.reference_response,
        allow_untrusted_code_execution=True,
    )

    exception_case, exception_node = _reviewed_pair("custom-ratio-missing-column")
    _install_worker_result(
        monkeypatch,
        _worker_result(
            exception_case,
            status="exception",
            exception={"type_name": "ValueError", "message": "wrong exception"},
        ),
    )
    exception_mismatch = evaluate_behavioral_proposal(
        exception_case,
        exception_node,
        exception_node.reference_response,
        allow_untrusted_code_execution=True,
    )

    assert output_mismatch.comparison.status == "mismatch"
    assert not output_mismatch.matched
    assert exception_mismatch.comparison.status == "mismatch"
    assert exception_mismatch.comparison.exception_matched is False


@pytest.mark.parametrize("status", ["setup_failure", "process_failure", "serialization_failure"])
def test_proposal_evaluation_preserves_worker_failures(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    case, node = _reviewed_pair()
    _install_worker_result(
        monkeypatch,
        _worker_result(case, status=status, diagnostic=f"{status} diagnostic"),
    )

    evaluation = evaluate_behavioral_proposal(
        case,
        node,
        node.reference_response,
        allow_untrusted_code_execution=True,
    )

    assert evaluation.execution.status == status
    assert evaluation.comparison.status == "execution_error"
    assert evaluation.comparison.diagnostic_message == f"{status} diagnostic"


def test_proposal_execution_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    case, node = _reviewed_pair()

    def fake_popen(*_args: object, **_kwargs: object) -> subprocess.Popen[bytes]:
        return cast("subprocess.Popen[bytes]", _FakeProcess(timeout=True))

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(execution, "_terminate_process_tree", lambda _process: None)

    result = execute_behavioral_proposal(
        case,
        node,
        node.reference_response,
        allow_untrusted_code_execution=True,
    )

    assert result.status == "timeout"
    assert result.diagnostic_message == "proposal execution exceeded 10 seconds"


def test_invalid_proposal_is_rejected_before_process_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, node = _reviewed_pair()

    def forbidden_popen(*_args: object, **_kwargs: object) -> subprocess.Popen[bytes]:
        raise AssertionError("worker must not start")

    monkeypatch.setattr(subprocess, "Popen", forbidden_popen)

    with pytest.raises(ValueError, match="Invalid node code"):
        execute_behavioral_proposal(
            case,
            node,
            node.invalid_examples[0].response,
            allow_untrusted_code_execution=True,
        )


def test_proposal_execution_requires_explicit_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case, node = _reviewed_pair()

    def forbidden_popen(*_args: object, **_kwargs: object) -> subprocess.Popen[bytes]:
        raise AssertionError("worker must not start")

    monkeypatch.setattr(subprocess, "Popen", forbidden_popen)

    for consent in (False, cast("Any", 1), cast("Any", "yes")):
        with pytest.raises(ValueError, match="allow_untrusted_code_execution=True"):
            execute_behavioral_proposal(
                case,
                node,
                node.reference_response,
                allow_untrusted_code_execution=consent,
            )


def test_proposal_evaluation_contract_rejects_inconsistent_reports() -> None:
    case, node = _reviewed_pair()
    execution_result = BehavioralExecutionResult(
        schema_version="1.0",
        case_id=case.case_id,
        node_code_case_id=case.node_code_case_id,
        status="exception",
        outputs=(),
        exception=BehavioralExecutionException("KeyError", "missing"),
        stdout="",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        duration_seconds=0,
    )
    comparison_result = BehavioralCaseComparison(
        schema_version="1.0",
        case_id=case.case_id,
        node_code_case_id=case.node_code_case_id,
        execution_status="exception",
        status="mismatch",
        diagnostic_message="unexpected exception",
    )
    evaluation = BehavioralProposalEvaluation(
        schema_version="1.0",
        case_id=case.case_id,
        node_code_case_id=case.node_code_case_id,
        request_id=node.request.request_id,
        task_id=node.request.task_id,
        response_sha256="a" * 64,
        execution=execution_result,
        comparison=comparison_result,
    )

    for changes, message in (
        ({"schema_version": "2.0"}, "schema version"),
        ({"request_id": ""}, "IDs"),
        ({"response_sha256": "invalid"}, "SHA-256"),
        ({"execution": object()}, "execution must use"),
        ({"comparison": object()}, "comparison must use"),
        ({"case_id": "other"}, "execution identity"),
        (
            {
                "comparison": replace(
                    comparison_result,
                    case_id="other",
                    node_code_case_id="other",
                )
            },
            "comparison identity",
        ),
        (
            {"comparison": replace(comparison_result, execution_status="success")},
            "statuses",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            replace(evaluation, **cast("Any", changes))

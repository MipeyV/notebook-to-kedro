"""Review identities, immutable inputs and honest terminal outcomes for generated tests."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from notebook_to_kedro import (
    GeneratedValidationRequest,
    GenerateRequest,
    generate_project,
    load_local_project_configuration,
    prepare_generated_validation,
    run_generated_validation,
)
from notebook_to_kedro.cli import main
from notebook_to_kedro.exceptions import LocalOperationError
from notebook_to_kedro.operations import generated_validation as execution
from notebook_to_kedro.operations import validation_cli as command_line
from notebook_to_kedro.operations import validation_process as processes
from notebook_to_kedro.operations import validation_snapshot as snapshots

ROOT = Path(__file__).parents[2]


@pytest.fixture
def request_case(tmp_path: Path) -> GeneratedValidationRequest:
    root = tmp_path / "case"
    shutil.copytree(ROOT / "examples/procedural_regression", root)
    config = load_local_project_configuration(root / "project.json")
    generate_project(GenerateRequest(config, root / "generated/project"))
    return GeneratedValidationRequest(
        config, root / "generated/project", Path(sys.executable), root / "validation"
    )


def _environment(output: Path, *, missing: bool = False) -> None:
    (output / "environment.json").write_text(
        json.dumps({"missing": ["pytest"] if missing else [], "distributions": {"pytest": "9"}}),
        encoding="utf-8",
    )


def _junit(output: Path, cases: str = "<testcase/>") -> None:
    (output / "pytest.xml").write_text(
        f"<testsuites><testsuite>{cases}</testsuite></testsuites>", encoding="utf-8"
    )


def _successful_worker(
    _python: Path, output: Path, _timeout: int, _cancel: threading.Event
) -> tuple[str, int, bool]:
    _environment(output)
    _junit(output)
    return "completed", 0, False


def test_review_is_readonly_and_binds_actual_project_runtime_and_budget(
    request_case: GeneratedValidationRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("Review must not execute"),
    )
    plan = prepare_generated_validation(request_case)
    assert not request_case.output.exists()
    assert plan.to_dict()["execution_status"] == "not_run"
    assert plan.to_dict()["snapshot_scope"] == "current_renderer_inventory_only"
    assert "not a security sandbox" in str(plan.to_dict()["execution_notice"])
    assert plan.sha256 == prepare_generated_validation(request_case).sha256
    assert (
        plan.sha256
        != prepare_generated_validation(replace(request_case, timeout_seconds=30)).sha256
    )
    exported = plan.to_dict()
    exported["files"] = []
    assert plan.to_dict()["files"]


@pytest.mark.parametrize("timeout", [True, False, 0, 601, 1.5])
def test_invalid_budget_is_refused(request_case: GeneratedValidationRequest, timeout: Any) -> None:
    with pytest.raises(LocalOperationError, match="timeout"):
        replace(request_case, timeout_seconds=timeout)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("python", "python"),
        ("python", Path("relative")),
        ("project", Path("missing")),
        ("output", Path("../escape")),
    ],
)
def test_invalid_paths_are_refused(
    request_case: GeneratedValidationRequest, field: str, value: Any
) -> None:
    with pytest.raises(LocalOperationError):
        replace(request_case, **{field: value})


def test_no_tests_and_functional_settings_are_explicitly_outside_initial_scope(
    request_case: GeneratedValidationRequest,
) -> None:
    with pytest.raises(LocalOperationError, match="notebook settings"):
        replace(
            request_case,
            configuration=replace(request_case.configuration, regression_contract=None),
        )
    with pytest.raises(LocalOperationError, match="notebook settings"):
        replace(
            request_case,
            configuration=replace(request_case.configuration, source_kind="functional"),
        )


@pytest.mark.parametrize(
    "relative",
    ["generated/project", "generated/project/attempt", ".", "workflow.ipynb", "regression.json"],
)
def test_output_must_not_overlap_protected_inputs(
    request_case: GeneratedValidationRequest, relative: str
) -> None:
    with pytest.raises(LocalOperationError):
        replace(request_case, output=Path(relative))


def test_stale_approval_and_modified_project_never_start_a_worker(
    request_case: GeneratedValidationRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        execution, "supervise_validation", lambda *_args: pytest.fail("must not execute")
    )
    with pytest.raises(LocalOperationError, match="stale"):
        run_generated_validation(request_case, approved_sha256="0" * 64)
    (request_case.project / "pyproject.toml").write_text("modified", encoding="utf-8")
    with pytest.raises(LocalOperationError, match="differs"):
        prepare_generated_validation(request_case)
    assert not request_case.output.exists()


def test_missing_project_file_and_bounded_inventory_refuse_review(
    request_case: GeneratedValidationRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(snapshots, "MAX_SNAPSHOT_FILES", 1)
    with pytest.raises(LocalOperationError, match="inventory"):
        prepare_generated_validation(request_case)
    monkeypatch.undo()
    (request_case.project / "pyproject.toml").unlink()
    with pytest.raises(LocalOperationError, match="Cannot read"):
        prepare_generated_validation(request_case)


def test_regular_contained_file_and_size_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = tmp_path / "file"
    file.write_bytes(b"abc")
    assert snapshots.file_identity(file, tmp_path)[1] == 3
    with pytest.raises(LocalOperationError, match="escapes"):
        snapshots.file_identity(file, tmp_path / "other")
    with pytest.raises(LocalOperationError, match="bounded"):
        snapshots.file_identity(file, tmp_path, 2)
    with pytest.raises(LocalOperationError, match="bounded"):
        snapshots.file_identity(tmp_path, tmp_path)
    original = Path.lstat
    monkeypatch.setattr(
        Path,
        "lstat",
        lambda self: (
            SimpleNamespace(st_mode=original(self).st_mode, st_file_attributes=0x400)
            if self == file
            else original(self)
        ),
    )
    with pytest.raises(LocalOperationError, match="links"):
        snapshots.file_identity(file, tmp_path)


def test_success_is_separate_evidence_and_only_copies_renderer_inventory(
    request_case: GeneratedValidationRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    (request_case.project / "unreviewed.py").write_text(
        "raise RuntimeError('never copy')", encoding="utf-8"
    )
    plan = prepare_generated_validation(request_case)
    monkeypatch.setattr(execution, "supervise_validation", _successful_worker)
    result = run_generated_validation(request_case, approved_sha256=plan.sha256)
    report = result.to_dict()
    assert report["status"] == "passed"
    assert report["tests"] == {"tests": 1, "passed": 1, "failed": 0, "errors": 0, "skipped": 0}
    assert all(
        report[key] is True
        for key in (
            "original_unchanged",
            "snapshot_unchanged",
            "inputs_unchanged",
            "python_unchanged",
        )
    )
    assert not (request_case.output / "project/unreviewed.py").exists()
    assert (
        json.loads((request_case.project / "regression-coverage.json").read_text())[
            "execution_status"
        ]
        == "not_run"
    )
    assert json.loads((request_case.output / "report.json").read_text()) == report
    written_worker_sha = hashlib.sha256(
        (request_case.output / "worker.py").read_bytes()
    ).hexdigest()
    assert written_worker_sha == plan.to_dict()["worker_sha256"]
    report["status"] = "changed"
    assert result.to_dict()["status"] == "passed"
    with pytest.raises(LocalOperationError):
        run_generated_validation(request_case, approved_sha256=plan.sha256)


@pytest.mark.parametrize(
    ("cases", "code", "expected"),
    [
        ("<testcase><failure/></testcase>", 1, "failed"),
        ("<testcase><error/></testcase>", 0, "failed"),
        ("<testcase><skipped/></testcase>", 0, "no_passing_tests"),
        ("", 5, "failed"),
        ("", 0, "no_passing_tests"),
        ("<testcase/>", 1, "failed"),
    ],
)
def test_failed_skipped_and_empty_suites_never_pass(
    request_case: GeneratedValidationRequest,
    monkeypatch: pytest.MonkeyPatch,
    cases: str,
    code: int,
    expected: str,
) -> None:
    plan = prepare_generated_validation(request_case)

    def worker(
        _python: Path, output: Path, _timeout: int, _cancel: threading.Event
    ) -> tuple[str, int, bool]:
        _environment(output)
        _junit(output, cases)
        return "completed", code, False

    monkeypatch.setattr(execution, "supervise_validation", worker)
    assert (
        run_generated_validation(request_case, approved_sha256=plan.sha256).to_dict()["status"]
        == expected
    )


@pytest.mark.parametrize("status", ["timed_out", "canceled", "cleanup_incomplete"])
def test_terminal_interruptions_are_durable(
    request_case: GeneratedValidationRequest, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    plan = prepare_generated_validation(request_case)
    monkeypatch.setattr(execution, "supervise_validation", lambda *_args: (status, -1, True))
    result = run_generated_validation(request_case, approved_sha256=plan.sha256).to_dict()
    assert result["status"] == status
    assert result["tests"] is None
    assert result["log_truncated"] is True
    assert (request_case.output / "report.json").is_file()


@pytest.mark.parametrize(
    "kind", ["missing", "absent", "invalid", "bad_xml", "dtd", "root", "inconsistent"]
)
def test_environment_and_report_failures_remain_visible(
    request_case: GeneratedValidationRequest, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    plan = prepare_generated_validation(request_case)

    def worker(
        _python: Path, output: Path, _timeout: int, _cancel: threading.Event
    ) -> tuple[str, int, bool]:
        if kind == "absent":
            return "completed", 3, False
        _environment(output, missing=kind == "missing")
        if kind == "invalid":
            (output / "environment.json").write_text("[]", encoding="utf-8")
        elif kind in {"bad_xml", "dtd", "root", "inconsistent"}:
            content = {
                "bad_xml": "<",
                "dtd": "<!DOCTYPE a><testsuite/>",
                "root": "<other/>",
                "inconsistent": "<testsuite><testcase><failure/><error/></testcase></testsuite>",
            }[kind]
            (output / "pytest.xml").write_text(content, encoding="utf-8")
        return "completed", 3, False

    monkeypatch.setattr(execution, "supervise_validation", worker)
    report = run_generated_validation(request_case, approved_sha256=plan.sha256).to_dict()
    assert report["status"] == ("environment_missing" if kind == "missing" else "runner_error")


@pytest.mark.parametrize("target", ["original", "snapshot", "input"])
def test_file_drift_cannot_be_promoted_to_success(
    request_case: GeneratedValidationRequest, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    plan = prepare_generated_validation(request_case)

    def worker(
        python: Path, output: Path, timeout: int, cancel: threading.Event
    ) -> tuple[str, int, bool]:
        result = _successful_worker(python, output, timeout, cancel)
        path = {
            "original": request_case.project / "pyproject.toml",
            "snapshot": output / "project/pyproject.toml",
            "input": request_case.configuration.source,
        }[target]
        path.write_bytes(b"changed")
        return result

    monkeypatch.setattr(execution, "supervise_validation", worker)
    assert (
        run_generated_validation(request_case, approved_sha256=plan.sha256).to_dict()["status"]
        == "drifted"
    )


def test_process_log_retention_is_bounded_and_drained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(processes, "MAX_LOG_BYTES", 8)
    for content in (b"short", b"12345678", b"long" * 10000):
        truncated = threading.Event()
        target = tmp_path / "log"
        processes._drain(io.BytesIO(content), target, truncated)
        assert target.read_bytes() == content[:8]
        assert truncated.is_set() == (len(content) > 8)


@pytest.mark.parametrize("mode", ["success", "timeout", "cancel", "before_start"])
def test_real_subprocess_supervision(tmp_path: Path, mode: str) -> None:
    (tmp_path / "project").mkdir()
    worker_code = (
        "print('worker completed')" if mode == "success" else "import time; time.sleep(30)"
    )
    (tmp_path / "worker.py").write_text(worker_code, encoding="utf-8")
    cancel = threading.Event()
    timer = None
    if mode == "before_start":
        cancel.set()
    elif mode == "cancel":
        timer = threading.Timer(0.2, cancel.set)
        timer.start()
    try:
        status, code, truncated = processes.supervise_validation(
            Path(sys.executable), tmp_path, 1 if mode == "timeout" else 10, cancel
        )
    finally:
        if timer:
            timer.cancel()
    assert (
        status
        == {
            "success": "completed",
            "timeout": "timed_out",
            "cancel": "canceled",
            "before_start": "canceled",
        }[mode]
    )
    assert truncated is False
    if mode == "success":
        assert code == 0
        assert b"worker completed" in (tmp_path / "tests.log").read_bytes()


def test_cli_review_and_explicit_run_have_separate_envelopes(
    request_case: GeneratedValidationRequest,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = [
        str(request_case.configuration.project_root / "project.json"),
        str(request_case.project),
        "--python",
        str(request_case.python),
        "--output",
        str(request_case.output),
    ]
    assert main(["project", "validation-plan", *args]) == 0
    review = json.loads(capsys.readouterr().out)
    assert review["execution_status"] == "not_run"
    monkeypatch.setattr(execution, "supervise_validation", _successful_worker)
    assert main(["project", "validate", *args, "--approved-sha256", review["plan_sha256"]]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "passed"


def test_file_growth_is_bounded_during_actual_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "growing"
    path.write_bytes(b"abc")
    monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: io.BytesIO(b"grew"))
    with pytest.raises(LocalOperationError, match="byte budget"):
        snapshots.file_identity(path, tmp_path, 3)


@pytest.mark.parametrize("stage", ["source", "copy"])
def test_copy_races_create_failed_evidence_without_execution(
    request_case: GeneratedValidationRequest, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    plan = prepare_generated_validation(request_case)
    monkeypatch.setattr(
        execution,
        "supervise_validation",
        lambda *_args: pytest.fail("Do not execute inconsistent copies"),
    )
    if stage == "source":
        identity = snapshots.file_identity
        monkeypatch.setattr(
            execution,
            "file_identity",
            lambda path, root, *args: (
                ("0" * 64, 0) if root == request_case.project else identity(path, root, *args)
            ),
        )
    else:
        monkeypatch.setattr(
            shutil, "copyfile", lambda _source, target: target.write_bytes(b"bad copy")
        )
    report = run_generated_validation(request_case, approved_sha256=plan.sha256).to_dict()
    assert report["status"] == "runner_error"
    assert report["error"]


@pytest.mark.parametrize("failure", ["deleted", "python_changed", "python_unreadable"])
def test_postflight_missing_or_changed_inputs_are_not_success(
    request_case: GeneratedValidationRequest, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    plan = prepare_generated_validation(request_case)

    def worker(
        python: Path, output: Path, timeout: int, cancel: threading.Event
    ) -> tuple[str, int, bool]:
        result = _successful_worker(python, output, timeout, cancel)
        if failure == "deleted":
            (request_case.project / "pyproject.toml").unlink()
        else:
            identity = snapshots.file_identity

            def changed(path: Path, root: Path, *args: int) -> tuple[str, int]:
                if path == request_case.python.resolve():
                    if failure == "python_unreadable":
                        raise OSError("Interpreter no longer readable")
                    return "0" * 64, 0
                return identity(path, root, *args)

            monkeypatch.setattr(execution, "file_identity", changed)
        return result

    monkeypatch.setattr(execution, "supervise_validation", worker)
    assert (
        run_generated_validation(request_case, approved_sha256=plan.sha256).to_dict()["status"]
        == "drifted"
    )


@pytest.mark.parametrize("text", ["cancel\n", ""])
def test_stdin_cancel_handles_line_and_client_disconnect(
    text: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    read_fd, write_fd = os.pipe()
    try:
        if text:
            os.write(write_fd, text.encode())
        os.close(write_fd)
        monkeypatch.setattr(sys, "stdin", SimpleNamespace(fileno=lambda: read_fd))
        event = threading.Event()
        command_line._stdin_cancel(event)
        assert event.is_set()
    finally:
        os.close(read_fd)


def test_cli_interrupt_handler_and_stdin_return_canceled_evidence(
    request_case: GeneratedValidationRequest,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:

    def canceled(
        _request: GeneratedValidationRequest, *, approved_sha256: str, cancel: threading.Event
    ) -> execution.GeneratedValidationResult:
        assert approved_sha256 == "a" * 64
        handler = signal.getsignal(signal.SIGINT)
        assert callable(handler)
        handler(signal.SIGINT, None)
        assert cancel.is_set()
        return execution.GeneratedValidationResult(json.dumps({"status": "canceled"}))

    monkeypatch.setattr(command_line, "run_generated_validation", canceled)
    monkeypatch.setattr(command_line, "_stdin_cancel", lambda event: event.set())
    args = [
        "project",
        "validate",
        str(request_case.configuration.project_root / "project.json"),
        str(request_case.project),
        "--python",
        str(request_case.python),
        "--output",
        str(request_case.output),
        "--approved-sha256",
        "a" * 64,
        "--cancellable-stdin",
    ]
    assert main(args) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "canceled"


def test_cli_oserror_is_a_diagnostic(
    request_case: GeneratedValidationRequest,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def failed(_request: GeneratedValidationRequest) -> None:
        raise OSError("Read refused")

    monkeypatch.setattr(command_line, "prepare_generated_validation", failed)
    assert (
        main(
            [
                "project",
                "validation-plan",
                str(request_case.configuration.project_root / "project.json"),
                str(request_case.project),
                "--python",
                str(request_case.python),
                "--output",
                str(request_case.output),
            ]
        )
        == 1
    )
    assert "Cannot prepare validation" in capsys.readouterr().err


@pytest.mark.parametrize("platform", ["win32", "linux"])
@pytest.mark.parametrize("already_exited", [False, True])
def test_process_tree_cleanup_platforms(
    platform: str, monkeypatch: pytest.MonkeyPatch, *, already_exited: bool
) -> None:
    calls: list[str] = []
    process: Any = SimpleNamespace(
        pid=123456,
        poll=lambda: 0 if already_exited else None,
        kill=lambda: calls.append("kill"),
        wait=lambda **_kwargs: calls.append("wait"),
    )
    monkeypatch.setattr(processes, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: calls.append("taskkill"))
    monkeypatch.setattr(os, "killpg", lambda *_args: calls.append("killpg"), raising=False)
    monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)
    processes.terminate_validation_process(process)
    assert calls == [
        "taskkill" if platform == "win32" else "killpg",
        *([] if already_exited else ["kill"]),
        "wait",
    ]


@pytest.mark.parametrize("incomplete", [False, True])
def test_completed_process_cancellation_and_incomplete_log_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, incomplete: bool
) -> None:
    event = threading.Event()

    def poll() -> int:
        event.set()
        return 0

    process: Any = SimpleNamespace(stdout=io.BytesIO(b""), returncode=0, poll=poll)
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)
    reader = SimpleNamespace(
        start=lambda: None, join=lambda **_kwargs: None, is_alive=lambda: incomplete
    )
    monkeypatch.setattr(threading, "Thread", lambda **_kwargs: reader)
    status, _, _ = processes.supervise_validation(Path(sys.executable), tmp_path, 1, event)
    assert status == ("cleanup_incomplete" if incomplete else "canceled")


def test_supervisor_reaps_worker_after_wait_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"running": True, "reaped": False}
    process: Any = SimpleNamespace(
        stdout=io.BytesIO(b""), returncode=None, poll=lambda: None if state["running"] else 0
    )

    def cleanup(_process: Any) -> None:
        state.update(running=False, reaped=True)

    def failed_wait(_seconds: float) -> None:
        raise OSError("Polling interrupted")

    event: Any = SimpleNamespace(is_set=lambda: False, wait=failed_wait)
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(processes, "terminate_validation_process", cleanup)
    reader = SimpleNamespace(start=lambda: None, join=lambda **_kwargs: None)
    monkeypatch.setattr(threading, "Thread", lambda **_kwargs: reader)
    with pytest.raises(OSError, match="Polling interrupted"):
        processes.supervise_validation(Path(sys.executable), tmp_path, 1, event)
    assert state["reaped"] is True


def test_execution_report_growth_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "report"
    path.write_bytes(b"1234")
    monkeypatch.setattr(execution, "file_identity", lambda *_args: ("a" * 64, 4))
    with pytest.raises(ValueError, match="byte budget"):
        execution._read_output(path, 3)


def test_log_failure_cannot_be_reported_as_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "project").mkdir()
    (tmp_path / "worker.py").write_text("pass", encoding="utf-8")

    def unreadable(stream: Any, _path: Path, _truncated: threading.Event) -> None:
        stream.close()
        raise OSError("Log destination refused")

    monkeypatch.setattr(processes, "_drain", unreadable)
    status, _code, _truncated = processes.supervise_validation(
        Path(sys.executable), tmp_path, 10, threading.Event()
    )
    assert status == "runner_error"


def test_inherited_pytest_plugin_requests_are_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "project").mkdir()
    (tmp_path / "worker.py").write_text(
        "import os; print(os.environ.get('PYTEST_PLUGINS', 'disabled'))", encoding="utf-8"
    )
    monkeypatch.setenv("PYTEST_PLUGINS", "unreviewed_plugin")
    status, code, _ = processes.supervise_validation(
        Path(sys.executable), tmp_path, 10, threading.Event()
    )
    assert status == "completed"
    assert code == 0
    assert (tmp_path / "tests.log").read_text().strip() == "disabled"

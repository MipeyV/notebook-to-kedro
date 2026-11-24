"""Explicit execution of reviewed delivered tests with separate durable evidence."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from notebook_to_kedro.exceptions import LocalOperationError
from notebook_to_kedro.operations.validation_process import WORKER, supervise_validation
from notebook_to_kedro.operations.validation_snapshot import (
    GeneratedValidationPlan,
    GeneratedValidationRequest,
    file_identity,
    prepare_generated_validation,
)


@dataclass(frozen=True, slots=True)
class GeneratedValidationResult:
    """Serialized immutable outcome; generated not_run manifests are never updated."""

    content: str

    def to_dict(self) -> dict[str, object]:
        """Export detached execution evidence, including failed and incomplete checks."""
        return dict(json.loads(self.content))


def _write(path: Path, payload: dict[str, object]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _unchanged(root: Path, files: tuple[tuple[str, str, int], ...]) -> bool:
    try:
        return all(
            file_identity(root / name, root) == (digest, size) for name, digest, size in files
        )
    except (OSError, LocalOperationError):
        return False


def _read_output(path: Path, limit: int) -> bytes:
    file_identity(path, path.parent, limit)
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Execution report exceeds its byte budget")
    return content


def _test_counts(path: Path) -> dict[str, int]:
    content = _read_output(path, 2 * 1024 * 1024)
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise ValueError("DTD/entity declarations are not supported in JUnit evidence")
    root = ET.fromstring(content)
    if root.tag not in {"testsuites", "testsuite"}:
        raise ValueError("Unsupported JUnit root")
    cases = list(root.iter("testcase"))
    counts = {
        name: sum(case.find(tag) is not None for case in cases)
        for name, tag in (("failed", "failure"), ("errors", "error"), ("skipped", "skipped"))
    }
    counts["tests"] = len(cases)
    counts["passed"] = len(cases) - counts["failed"] - counts["errors"] - counts["skipped"]
    if counts["passed"] < 0:
        raise ValueError("Inconsistent JUnit outcomes")
    return counts


def _classify(
    output: Path, process_status: str, returncode: int | None
) -> tuple[str, dict[str, object] | None, dict[str, int] | None]:
    if process_status != "completed":
        return process_status, None, None
    environment = None
    environment_path = output / "environment.json"
    if environment_path.exists():
        environment = json.loads(_read_output(environment_path, 65_536).decode("utf-8"))
        if not isinstance(environment, dict) or not isinstance(environment.get("missing"), list):
            raise ValueError("Invalid environment report")
    if environment is None:
        return "runner_error", None, None
    if environment["missing"]:
        return "environment_missing", environment, None
    counts = _test_counts(output / "pytest.xml")
    if returncode != 0 or counts["failed"] or counts["errors"]:
        return "failed", environment, counts
    if counts["passed"] == 0:
        return "no_passing_tests", environment, counts
    return "passed", environment, counts


def _copy_snapshot(plan: GeneratedValidationPlan) -> Path:
    request = plan.request
    snapshot = request.output / "project"
    snapshot.mkdir()
    for name, digest, size in plan.files:
        source, target = request.project / name, snapshot / name
        if file_identity(source, request.project) != (digest, size):
            raise LocalOperationError("GV002", "Project changed while preparing its execution copy")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if file_identity(target, snapshot) != (digest, size):
            raise LocalOperationError("GV002", "Execution copy differs from the reviewed project")
    return snapshot


def run_generated_validation(
    request: GeneratedValidationRequest,
    *,
    approved_sha256: str,
    cancel: threading.Event | None = None,
) -> GeneratedValidationResult:
    """Recheck explicit approval, execute one private snapshot and preserve terminal evidence.

    Args:
        request: Existing source/project, selected Python and new bounded attempt directory.
        approved_sha256: Identity returned by the reviewed prepare call, not a fixture approval.
        cancel: Cooperative cancellation signal; the supervisor terminates the worker tree/group.

    Returns:
        A separate run report. Success establishes only the supplied tests on captured files.

    """
    plan = prepare_generated_validation(request)
    if approved_sha256 != plan.sha256:
        raise LocalOperationError("GV002", "Validation review is stale or not explicitly approved")
    request = plan.request
    request.output.mkdir(parents=True)
    _write(request.output / "plan.json", plan.to_dict())
    started_at = datetime.now(UTC).isoformat()
    _write(
        request.output / "attempt.json",
        {"status": "started", "plan_sha256": plan.sha256, "started_at": started_at},
    )
    started = time.monotonic_ns()
    environment, counts, error = None, None, None
    returncode, truncated = None, False
    worker_duration_ns = None
    try:
        _copy_snapshot(plan)
        (request.output / "worker.py").write_text(WORKER, encoding="utf-8", newline="\n")
        worker_started = time.monotonic_ns()
        process_status, returncode, truncated = supervise_validation(
            request.python,
            request.output,
            request.timeout_seconds,
            cancel or threading.Event(),
        )
        worker_duration_ns = time.monotonic_ns() - worker_started
        status, environment, counts = _classify(request.output, process_status, returncode)
    except (
        OSError,
        ValueError,
        LocalOperationError,
        ET.ParseError,
        subprocess.SubprocessError,
    ) as exception:
        status, error = "runner_error", str(exception)
    original_unchanged = _unchanged(request.project, plan.files)
    snapshot_unchanged = _unchanged(request.output / "project", plan.files)
    inputs_unchanged = _unchanged(request.configuration.project_root, plan.inputs)
    try:
        python_path = request.python.resolve()
        python_unchanged = (
            file_identity(python_path, Path(python_path.anchor))[0] == plan.python_sha256
        )
    except (OSError, LocalOperationError):
        python_unchanged = False
    if status == "passed" and not all(
        (original_unchanged, snapshot_unchanged, inputs_unchanged, python_unchanged)
    ):
        status = "drifted"
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "operation": "validate",
        "status": status,
        "plan_sha256": plan.sha256,
        "project": str(request.project),
        "output": str(request.output),
        "python": str(request.python),
        "environment": environment,
        "tests": counts,
        "duration_ns": time.monotonic_ns() - started,
        "duration_scope": "copy_worker_evidence_postflight_only",
        "worker_duration_ns": worker_duration_ns,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "returncode": returncode,
        "log": "tests.log",
        "log_truncated": truncated,
        "error": error,
        "original_unchanged": original_unchanged,
        "snapshot_unchanged": snapshot_unchanged,
        "inputs_unchanged": inputs_unchanged,
        "python_unchanged": python_unchanged,
        "scope": "supplied_notebook_tests_on_private_renderer_inventory",
        "scientific_acceptance": "not_established",
        "installation": "not_performed",
    }
    _write(request.output / "report.json", payload)
    return GeneratedValidationResult(json.dumps(payload))

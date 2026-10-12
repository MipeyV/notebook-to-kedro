"""Consent-gated execution and draft comparison of complete captured notebook pipelines."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from notebook_to_kedro.evaluation.behavioral import behavior_value_to_dict
from notebook_to_kedro.evaluation.behavioral_artifacts import _json_sha256
from notebook_to_kedro.evaluation.behavioral_comparison import _compare_output
from notebook_to_kedro.evaluation.behavioral_execution import (
    BEHAVIORAL_EXECUTION_SCHEMA_VERSION,
    BehavioralExecutionConfig,
    BehavioralExecutionResult,
    _result_from_worker,
    _start_worker,
    _terminate_process_tree,
    _worker_directory,
)
from notebook_to_kedro.evaluation.behavioral_worker import _BoundedTextCapture
from notebook_to_kedro.evaluation.notebook_capture import load_notebook_body_capture
from notebook_to_kedro.evaluation.notebook_runtime import (
    NotebookRuntimeIdentity,
    collect_notebook_runtime_identity,
)
from notebook_to_kedro.evaluation.notebook_sources import (
    _read_file,
    _reject_constant,
    validate_source_bound_notebook_body_batch,
    verify_notebook_source_binding,
)
from notebook_to_kedro.generation.code.serialization import _unique_object
from notebook_to_kedro.generation.kedro import generate_kedro_project

if TYPE_CHECKING:
    from collections.abc import Sequence

    from notebook_to_kedro.evaluation.behavioral import ExpectedBehaviorOutput
    from notebook_to_kedro.evaluation.behavioral_execution import BehavioralExecutionStatus
    from notebook_to_kedro.evaluation.notebook_capture import NotebookBodyCapture
    from notebook_to_kedro.evaluation.notebook_sources import (
        NotebookSourceBinding,
        SourceBoundNotebookBodyReport,
    )

NOTEBOOK_PIPELINE_EXECUTION_VERSION = "notebook-pipeline-execution-draft-1"
_PACKAGE = "notebook_evaluation"
_WORKER = "notebook_to_kedro.evaluation.notebook_worker"


@dataclass(frozen=True, slots=True)
class NotebookObservation:
    """One named dataset and explicit bounded JSON observation adapter."""

    dataset: str
    kind: Literal["value", "series", "decision_tree"] = "value"

    def __post_init__(self) -> None:
        if not isinstance(self.dataset, str) or not self.dataset.strip():
            raise ValueError("observation dataset must be a non-empty string")
        if self.kind not in ("value", "series", "decision_tree"):
            raise ValueError("unsupported notebook observation kind")


@dataclass(frozen=True, slots=True)
class NotebookPipelineRun:
    """One draft complete-pipeline outcome, never an approved model benchmark score."""

    schema_version: str
    capture: NotebookBodyCapture
    static: SourceBoundNotebookBodyReport
    observations: tuple[NotebookObservation, ...]
    configuration: BehavioralExecutionConfig
    module_sha256: str | None
    request_sha256: str | None
    execution: BehavioralExecutionResult | None
    runtime_before: NotebookRuntimeIdentity | None = None
    runtime_after: NotebookRuntimeIdentity | None = None


@dataclass(frozen=True, slots=True)
class NotebookObservableComparison:
    """One output difference or explicit not-evaluated outcome."""

    dataset: str
    status: Literal["matched", "mismatch", "not_evaluated"]
    diagnostic_message: str | None


@dataclass(frozen=True, slots=True)
class NotebookPipelineComparison:
    """Draft caller-supplied expectation comparison, without human approval."""

    schema_version: str
    capture_sha256: str
    expectations_sha256: str
    status: Literal["matched", "mismatch", "not_evaluated"]
    outputs: tuple[NotebookObservableComparison, ...]


def _file_payload(path: str, data: bytes) -> dict[str, object]:
    return {
        "path": path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "data": base64.b64encode(data).decode("ascii"),
    }


def _prepare_project(
    directory: Path,
    binding: NotebookSourceBinding,
    module: str,
    root: Path,
    config: BehavioralExecutionConfig,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    snapshots = []
    size = 0
    for identity in binding.files:
        current, data = _read_file(root, identity.path, identity.role, binding.max_file_bytes)
        if current != identity:
            raise ValueError("execution source snapshot does not match binding")
        size += len(data)
        if size > config.max_request_bytes:
            raise ValueError("execution snapshots exceed max_request_bytes")
        path = directory / "inputs" / identity.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        snapshots.append(_file_payload(identity.path, data))
    dataset_paths = {i.role: directory / "inputs" / i.path for i in binding.files}
    plan = replace(
        binding.plan,
        catalog_datasets=tuple(
            replace(dataset, source_filepath=str(dataset_paths[f"dataset:{dataset.name}"]))
            for dataset in binding.plan.catalog_datasets
        ),
    )
    project = directory / "project"
    paths = generate_kedro_project(plan, project, package_name=_PACKAGE)
    nodes = project / "src" / _PACKAGE / "pipelines/notebook_pipeline/nodes.py"
    nodes.write_text(module, encoding="utf-8", newline="\n")
    if (project / "conf/base/catalog.yml").read_bytes() != dataset_paths[
        "expected_catalog"
    ].read_bytes():
        raise ValueError("generated catalog does not match bound expected catalog")
    files = []
    for path in paths:
        data = path.read_bytes()
        size += len(data)
        if size > config.max_request_bytes:
            raise ValueError("execution project exceeds max_request_bytes")
        files.append(_file_payload(path.relative_to(project).as_posix(), data))
    verify_notebook_source_binding(binding, project_root=root)
    return snapshots, files


def _failed(
    capture: NotebookBodyCapture,
    status: BehavioralExecutionStatus,
    duration: float,
    message: str,
) -> BehavioralExecutionResult:
    return BehavioralExecutionResult(
        BEHAVIORAL_EXECUTION_SCHEMA_VERSION,
        capture.binding.case_id,
        capture.content_sha256,
        status,
        (),
        None,
        "",
        "",
        stdout_truncated=False,
        stderr_truncated=False,
        duration_seconds=duration,
        diagnostic_message=message,
    )


def _execute(
    directory: Path,
    payload: dict[str, object],
    capture: NotebookBodyCapture,
    config: BehavioralExecutionConfig,
) -> tuple[str, BehavioralExecutionResult]:
    encoded = json.dumps(payload, ensure_ascii=True, allow_nan=False).encode("utf-8")
    if len(encoded) > config.max_request_bytes:
        raise ValueError("execution envelope exceeds max_request_bytes")
    digest = hashlib.sha256(encoded).hexdigest()
    request = directory / "request.json"
    result = directory / "result.json"
    request.write_bytes(encoded)
    started = time.perf_counter()
    command = (
        sys.executable,
        "-I",
        "-m",
        _WORKER,
        str(request),
        str(result),
        str(config.max_request_bytes),
        str(config.max_result_bytes),
        digest,
    )
    try:
        process = _start_worker(command, directory)
    except OSError as error:
        return digest, _failed(capture, "setup_failure", time.perf_counter() - started, str(error))
    try:
        code = process.wait(timeout=config.timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        return digest, _failed(
            capture,
            "timeout",
            time.perf_counter() - started,
            "whole-notebook worker exceeded timeout_seconds",
        )
    duration = time.perf_counter() - started
    if code != 0:
        return digest, _failed(
            capture, "process_failure", duration, f"worker exited with code {code}"
        )
    try:
        if not result.is_file() or not result.resolve().is_relative_to(directory.resolve()):
            raise ValueError("worker result must be a regular file contained in its directory")
        with result.open("rb") as stream:
            data = stream.read(config.max_result_bytes + 1)
        if len(data) > config.max_result_bytes:
            raise ValueError("worker observation exceeds max_result_bytes")
        execution = _result_from_worker(
            json.loads(data, object_pairs_hook=_unique_object, parse_constant=_reject_constant),
            duration,
        )
        if any(
            len(text.encode("utf-8")) > config.max_capture_bytes
            for text in (execution.stdout, execution.stderr)
        ):
            raise ValueError("worker logs exceed max_capture_bytes")
        if (execution.case_id, execution.node_code_case_id) != (
            capture.binding.case_id,
            capture.content_sha256,
        ):
            raise ValueError("worker result identity mismatch")
        if execution.status == "success" and tuple(
            o.output_name for o in execution.outputs
        ) != tuple(
            item["dataset"] for item in cast("list[dict[str, str]]", payload["observations"])
        ):
            raise ValueError("worker output inventory mismatch")
        return digest, execution
    except (OSError, ValueError) as error:
        return digest, _failed(capture, "process_failure", duration, str(error))


def run_notebook_pipeline_capture(  # noqa: PLR0913
    directory: str | Path,
    binding: NotebookSourceBinding,
    observations: Sequence[NotebookObservation],
    *,
    project_root: str | Path,
    allow_untrusted_code_execution: bool = False,
    config: BehavioralExecutionConfig | None = None,
    expected_capture_sha256: str | None = None,
) -> NotebookPipelineRun:
    """Revalidate captured bodies, snapshot inputs and run one complete DAG after consent."""
    if allow_untrusted_code_execution is not True:
        raise ValueError(
            "notebook pipeline requires allow_untrusted_code_execution=True; "
            "subprocess is not an OS sandbox"
        )
    settings = config or BehavioralExecutionConfig(
        timeout_seconds=60,
        max_request_bytes=16_777_216,
        max_result_bytes=4_194_304,
    )
    capture = load_notebook_body_capture(directory, binding, project_root=project_root)
    if expected_capture_sha256 is not None and capture.content_sha256 != expected_capture_sha256:
        raise ValueError("execution capture does not match frozen replay identity")
    targets = tuple(observations)
    produced = {name for task in binding.plan.task_candidates for name in task.outputs}
    if not targets or any(not isinstance(item, NotebookObservation) for item in targets):
        raise ValueError("observations must contain NotebookObservation values")
    names = tuple(item.dataset for item in targets)
    if len(set(names)) != len(names) or not set(names) <= produced:
        raise ValueError("observations require unique planned task outputs")
    static = validate_source_bound_notebook_body_batch(
        binding,
        capture.records,
        project_root=project_root,
        max_response_bytes=capture.max_response_bytes,
    )
    module = static.batch.module_source
    result = NotebookPipelineRun(
        NOTEBOOK_PIPELINE_EXECUTION_VERSION,
        capture,
        static,
        targets,
        settings,
        None,
        None,
        None,
        runtime_before=collect_notebook_runtime_identity(project_root),
    )
    if module is None:
        return replace(result, runtime_after=collect_notebook_runtime_identity(project_root))
    with _worker_directory() as workspace:
        sources, files = _prepare_project(
            workspace, binding, module, Path(project_root).resolve(), settings
        )
        payload: dict[str, object] = {
            "schema_version": NOTEBOOK_PIPELINE_EXECUTION_VERSION,
            "case_id": binding.case_id,
            "node_code_case_id": capture.content_sha256,
            "source_files": sources,
            "project_files": files,
            "observations": [asdict(item) for item in targets],
            "nodes": [
                {
                    "name": r.node_name,
                    "inputs": [*r.inputs, *(f"params:{p}" for p in r.parameter_names)],
                    "outputs": list(r.outputs),
                }
                for r in binding.requests
            ],
            "max_capture_bytes": settings.max_capture_bytes,
        }
        digest, execution = _execute(workspace, payload, capture, settings)
    return replace(
        result,
        module_sha256=hashlib.sha256(module.encode("utf-8")).hexdigest(),
        request_sha256=digest,
        execution=execution,
        runtime_after=collect_notebook_runtime_identity(project_root),
    )


def compare_notebook_pipeline_run(
    run: NotebookPipelineRun,
    expectations: Sequence[ExpectedBehaviorOutput],
) -> NotebookPipelineComparison:
    """Compare every requested observable with explicit draft expectations, never approve them."""
    expected = tuple(expectations)
    if tuple(item.output_name for item in expected) != tuple(
        item.dataset for item in run.observations
    ):
        raise ValueError("expectations must match the exact observation inventory")
    digest = _json_sha256(
        {
            "expectations": [
                {
                    "name": item.output_name,
                    "value": behavior_value_to_dict(item.value),
                    "comparison": asdict(item.comparison),
                }
                for item in expected
            ]
        }
    )
    execution = run.execution
    if execution is not None and (
        not run.static.batch.static_ready
        or (execution.case_id, execution.node_code_case_id)
        != (run.capture.binding.case_id, run.capture.content_sha256)
    ):
        raise ValueError("execution does not match the statically ready capture")
    comparisons = []
    if execution is None or execution.status != "success":
        status: Literal["matched", "mismatch", "not_evaluated"] = "not_evaluated"
        diagnostic = (
            "pipeline not executed" if execution is None else f"execution {execution.status}"
        )
        comparisons = [
            NotebookObservableComparison(item.output_name, status, diagnostic) for item in expected
        ]
    else:
        if tuple(item.output_name for item in execution.outputs) != tuple(
            item.output_name for item in expected
        ):
            raise ValueError("execution outputs do not match comparison inventory")
        for item, actual in zip(expected, execution.outputs, strict=True):
            compared = _compare_output(item, actual.value)
            text = _BoundedTextCapture(run.configuration.max_capture_bytes)
            text.write(compared.diagnostic_message or "")
            comparisons.append(
                NotebookObservableComparison(
                    item.output_name,
                    "matched" if compared.matched else "mismatch",
                    None if compared.matched else text.getvalue(),
                )
            )
        status = "matched" if all(item.status == "matched" for item in comparisons) else "mismatch"
    return NotebookPipelineComparison(
        NOTEBOOK_PIPELINE_EXECUTION_VERSION,
        run.capture.content_sha256,
        digest,
        status,
        tuple(comparisons),
    )

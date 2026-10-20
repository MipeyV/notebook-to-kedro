"""Integrity-bound draft pipeline reports and consent-gated offline replay."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from notebook_to_kedro.evaluation.behavioral import _output, behavior_value_to_dict
from notebook_to_kedro.evaluation.behavioral_artifacts import (
    _exact_keys,
    _integer,
    _is_sha256,
    _json_sha256,
    _number,
    _object,
    _optional_string,
    _string,
    _to_json,
    write_json_exclusive,
)
from notebook_to_kedro.evaluation.behavioral_execution import (
    BehavioralExecutionConfig,
    _result_from_worker,
    behavioral_execution_result_to_dict,
)
from notebook_to_kedro.evaluation.notebook_capture import load_notebook_body_capture
from notebook_to_kedro.evaluation.notebook_execution import (
    NOTEBOOK_PIPELINE_EXECUTION_VERSION,
    NotebookObservation,
    NotebookPipelineComparison,
    NotebookPipelineRun,
    compare_notebook_pipeline_run,
    run_notebook_pipeline_capture,
)
from notebook_to_kedro.evaluation.notebook_runtime import (
    NotebookRuntimeIdentity,
    collect_notebook_runtime_identity,
    require_notebook_runtime_compatibility,
)
from notebook_to_kedro.evaluation.notebook_sources import (
    _reject_constant,
    validate_source_bound_notebook_body_batch,
)
from notebook_to_kedro.generation.code.serialization import _unique_object

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Literal

    from notebook_to_kedro.evaluation.behavioral import ExpectedBehaviorOutput
    from notebook_to_kedro.evaluation.behavioral_execution import BehavioralExecutionResult
    from notebook_to_kedro.evaluation.notebook_sources import NotebookSourceBinding

NOTEBOOK_PIPELINE_ARTIFACT_VERSION = "notebook-pipeline-artifact-draft-1"
DEFAULT_NOTEBOOK_ARTIFACT_BYTES = 33_554_432
_PACKAGE_FIELDS = 2


@dataclass(frozen=True, slots=True)
class NotebookPipelineArtifact:
    """An inspectable draft outcome, not approved evidence or a model score."""

    schema_version: str
    run: NotebookPipelineRun
    expectations: tuple[ExpectedBehaviorOutput, ...]
    comparison: NotebookPipelineComparison
    source_artifact_sha256: str | None = None


def _digest(value: object, label: str) -> str:
    digest = _string(value, label)
    if not _is_sha256(digest):
        raise ValueError(f"{label} must be a lowercase SHA256")
    return digest


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _runtime(value: object) -> NotebookRuntimeIdentity:
    data = _object(value, "runtime")
    _exact_keys(data, frozenset(NotebookRuntimeIdentity.__dataclass_fields__), "runtime")
    packages = []
    for row in _array(data["packages"], "runtime packages"):
        fields = _array(row, "runtime package")
        if len(fields) != _PACKAGE_FIELDS:
            raise ValueError("runtime package requires name and version")
        packages.append((_string(fields[0], "package"), _optional_string(fields[1], "version")))
    lock = data["lock_sha256"]
    return NotebookRuntimeIdentity(
        _string(data["python_version"], "python_version"),
        _string(data["implementation"], "implementation"),
        _string(data["platform"], "platform"),
        _string(data["machine"], "machine"),
        tuple(packages),
        None if lock is None else _digest(lock, "lock_sha256"),
        _digest(data["package_sha256"], "package_sha256"),
    )


def _validate_run(run: NotebookPipelineRun) -> None:
    if run.schema_version != NOTEBOOK_PIPELINE_EXECUTION_VERSION:
        raise ValueError("unsupported notebook execution version")
    if run.static.binding != run.capture.binding:
        raise ValueError("static report binding mismatch")
    if run.runtime_before is None or run.runtime_after is None:
        raise ValueError("runtime identities must be recorded at execution time")
    _number(run.configuration.timeout_seconds, "timeout_seconds")
    # Revalidate runtime values supplied directly by Python callers as well as parsed JSON.
    _runtime(json.loads(_to_json(asdict(run.runtime_before))))
    _runtime(json.loads(_to_json(asdict(run.runtime_after))))
    names = tuple(item.dataset for item in run.observations)
    produced = {name for task in run.capture.binding.plan.task_candidates for name in task.outputs}
    if not names or len(set(names)) != len(names) or not set(names) <= produced:
        raise ValueError("artifact observations require unique planned outputs")
    module = run.static.batch.module_source
    if module is None:
        if any(
            value is not None for value in (run.module_sha256, run.request_sha256, run.execution)
        ):
            raise ValueError("blocked static report cannot contain execution evidence")
    else:
        if run.module_sha256 != hashlib.sha256(module.encode("utf-8")).hexdigest():
            raise ValueError("artifact module digest mismatch")
        _digest(run.request_sha256, "request_sha256")
        if run.execution is None:
            raise ValueError("statically ready artifact requires an execution outcome")
    if run.execution is not None:
        if any(
            len(text.encode("utf-8")) > run.configuration.max_capture_bytes
            for text in (run.execution.stdout, run.execution.stderr)
        ):
            raise ValueError("artifact logs exceed max_capture_bytes")
        result = behavioral_execution_result_to_dict(run.execution)
        duration = _number(result.pop("duration_seconds"), "duration_seconds")
        _result_from_worker(result, duration)


def create_notebook_pipeline_artifact(
    run: NotebookPipelineRun,
    expectations: Sequence[ExpectedBehaviorOutput],
    *,
    source_artifact_sha256: str | None = None,
) -> NotebookPipelineArtifact:
    """Retain every static/runtime outcome and recompute explicit draft comparisons."""
    _validate_run(run)
    if source_artifact_sha256 is not None:
        _digest(source_artifact_sha256, "source_artifact_sha256")
    expected = tuple(
        _output(
            {
                "output_name": item.output_name,
                "value": behavior_value_to_dict(item.value),
                "comparison": asdict(item.comparison),
            }
        )
        for item in expectations
    )
    return NotebookPipelineArtifact(
        NOTEBOOK_PIPELINE_ARTIFACT_VERSION,
        run,
        expected,
        compare_notebook_pipeline_run(run, expected),
        source_artifact_sha256,
    )


def _execution_payload(execution: BehavioralExecutionResult) -> dict[str, object]:
    payload = behavioral_execution_result_to_dict(execution)
    payload["duration_seconds"] = float(execution.duration_seconds)
    return payload


def notebook_pipeline_artifact_to_dict(artifact: NotebookPipelineArtifact) -> dict[str, object]:
    """Serialize an outcome with exact capture, static, expectation and runtime identities."""
    checked = create_notebook_pipeline_artifact(
        artifact.run, artifact.expectations, source_artifact_sha256=artifact.source_artifact_sha256
    )
    if artifact != checked:
        raise ValueError("artifact version or comparison mismatch")
    run = artifact.run
    payload: dict[str, object] = {
        "schema_version": artifact.schema_version,
        "source_artifact_sha256": artifact.source_artifact_sha256,
        "capture": asdict(run.capture),
        "static": asdict(run.static.batch),
        "observations": [asdict(item) for item in run.observations],
        "configuration": {
            **asdict(run.configuration),
            "timeout_seconds": float(run.configuration.timeout_seconds),
        },
        "module_sha256": run.module_sha256,
        "request_sha256": run.request_sha256,
        "runtime_before": asdict(cast("NotebookRuntimeIdentity", run.runtime_before)),
        "runtime_after": asdict(cast("NotebookRuntimeIdentity", run.runtime_after)),
        "execution": None if run.execution is None else _execution_payload(run.execution),
        "expectations": [
            {
                "output_name": item.output_name,
                "value": behavior_value_to_dict(item.value),
                "comparison": asdict(item.comparison),
            }
            for item in artifact.expectations
        ],
        "comparison": asdict(artifact.comparison),
    }
    # Normalize tuples before equality checks; canonical JSON distinguishes bool from int.
    normalized = _object(json.loads(_to_json(payload)), "artifact")
    return {**normalized, "content_sha256": _json_sha256(normalized)}


def _limit(value: int) -> None:
    if _integer(value, "max_file_bytes") <= 0:
        raise ValueError("max_file_bytes must be positive")


def write_notebook_pipeline_artifact(
    path: str | Path,
    artifact: NotebookPipelineArtifact,
    *,
    max_file_bytes: int = DEFAULT_NOTEBOOK_ARTIFACT_BYTES,
) -> Path:
    """Publish a bounded report exclusively, never overwrite existing evidence."""
    _limit(max_file_bytes)
    payload = notebook_pipeline_artifact_to_dict(artifact)
    if len(_to_json(payload).encode("utf-8")) > max_file_bytes:
        raise ValueError("notebook artifact exceeds max_file_bytes")
    destination = Path(path)
    write_json_exclusive(destination, payload)
    return destination


def load_notebook_pipeline_artifact(
    path: str | Path,
    binding: NotebookSourceBinding,
    capture_directory: str | Path,
    *,
    project_root: str | Path,
    max_file_bytes: int = DEFAULT_NOTEBOOK_ARTIFACT_BYTES,
) -> NotebookPipelineArtifact:
    """Verify bytes, sources, capture and recomputed static/comparison evidence; never execute."""
    _limit(max_file_bytes)
    source = Path(path)
    if not source.is_file():
        raise ValueError("notebook artifact must be a regular file")
    with source.open("rb") as stream:
        raw = stream.read(max_file_bytes + 1)
    if len(raw) > max_file_bytes:
        raise ValueError("notebook artifact exceeds max_file_bytes")
    data = _object(
        json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant),
        "artifact",
    )
    return notebook_pipeline_artifact_from_dict(
        data, binding, capture_directory, project_root=project_root
    )


def notebook_pipeline_artifact_from_dict(
    payload: object,
    binding: NotebookSourceBinding,
    capture_directory: str | Path,
    *,
    project_root: str | Path,
) -> NotebookPipelineArtifact:
    """Recheck structured artifact evidence against current sources without executing it."""
    data = _object(payload, "artifact")
    keys = frozenset(
        {
            "schema_version",
            "source_artifact_sha256",
            "capture",
            "static",
            "observations",
            "configuration",
            "module_sha256",
            "request_sha256",
            "runtime_before",
            "runtime_after",
            "execution",
            "expectations",
            "comparison",
            "content_sha256",
        }
    )
    _exact_keys(data, keys, "notebook artifact")
    if data["schema_version"] != NOTEBOOK_PIPELINE_ARTIFACT_VERSION:
        raise ValueError("unsupported notebook artifact version")
    digest = _digest(data["content_sha256"], "content_sha256")
    if digest != _json_sha256(
        {key: value for key, value in data.items() if key != "content_sha256"}
    ):
        raise ValueError("notebook artifact integrity mismatch")
    capture = load_notebook_body_capture(capture_directory, binding, project_root=project_root)
    static = validate_source_bound_notebook_body_batch(
        binding,
        capture.records,
        project_root=project_root,
        max_response_bytes=capture.max_response_bytes,
    )
    observations = []
    for item in _array(data["observations"], "observations"):
        row = _object(item, "observation")
        _exact_keys(row, frozenset({"dataset", "kind"}), "observation")
        observations.append(
            NotebookObservation(
                _string(row["dataset"], "dataset"),
                cast("Literal['value', 'series', 'decision_tree']", _string(row["kind"], "kind")),
            )
        )
    config = _object(data["configuration"], "configuration")
    _exact_keys(config, frozenset(BehavioralExecutionConfig.__dataclass_fields__), "configuration")
    settings = BehavioralExecutionConfig(
        _number(config["timeout_seconds"], "timeout_seconds"),
        *(
            _integer(config[name], name)
            for name in ("max_request_bytes", "max_result_bytes", "max_capture_bytes")
        ),
    )
    execution = None
    if data["execution"] is not None:
        result = dict(_object(data["execution"], "execution"))
        duration = _number(result.pop("duration_seconds", None), "duration_seconds")
        execution = _result_from_worker(result, duration)
    run = NotebookPipelineRun(
        NOTEBOOK_PIPELINE_EXECUTION_VERSION,
        capture,
        static,
        tuple(observations),
        settings,
        _optional_string(data["module_sha256"], "module_sha256"),
        _optional_string(data["request_sha256"], "request_sha256"),
        execution,
        _runtime(data["runtime_before"]),
        _runtime(data["runtime_after"]),
    )
    artifact = create_notebook_pipeline_artifact(
        run,
        tuple(_output(item) for item in _array(data["expectations"], "expectations")),
        source_artifact_sha256=_optional_string(
            data["source_artifact_sha256"], "source_artifact_sha256"
        ),
    )
    if _json_sha256(notebook_pipeline_artifact_to_dict(artifact)) != _json_sha256(data):
        raise ValueError("notebook artifact capture, static or comparison evidence mismatch")
    return artifact


def replay_notebook_pipeline_artifact(  # noqa: PLR0913
    path: str | Path,
    binding: NotebookSourceBinding,
    capture_directory: str | Path,
    *,
    project_root: str | Path,
    allow_untrusted_code_execution: bool = False,
    max_file_bytes: int = DEFAULT_NOTEBOOK_ARTIFACT_BYTES,
) -> NotebookPipelineArtifact:
    """Renew consent, refuse incompatible controls and recompute an outcome without model I/O."""
    if allow_untrusted_code_execution is not True:
        raise ValueError(
            "artifact replay requires allow_untrusted_code_execution=True; "
            "subprocess is not an OS sandbox"
        )
    artifact = load_notebook_pipeline_artifact(
        path, binding, capture_directory, project_root=project_root, max_file_bytes=max_file_bytes
    )
    before = cast("NotebookRuntimeIdentity", artifact.run.runtime_before)
    after = cast("NotebookRuntimeIdentity", artifact.run.runtime_after)
    require_notebook_runtime_compatibility(
        before, after, collect_notebook_runtime_identity(project_root)
    )
    run = run_notebook_pipeline_capture(
        capture_directory,
        binding,
        artifact.run.observations,
        project_root=project_root,
        allow_untrusted_code_execution=True,
        config=artifact.run.configuration,
        expected_capture_sha256=artifact.run.capture.content_sha256,
    )
    if (run.capture, run.module_sha256, run.request_sha256) != (
        artifact.run.capture,
        artifact.run.module_sha256,
        artifact.run.request_sha256,
    ):
        raise ValueError("replay capture or execution request identity mismatch")
    require_notebook_runtime_compatibility(
        before,
        cast("NotebookRuntimeIdentity", run.runtime_before),
        cast("NotebookRuntimeIdentity", run.runtime_after),
    )
    return create_notebook_pipeline_artifact(
        run,
        artifact.expectations,
        source_artifact_sha256=cast(
            "str", notebook_pipeline_artifact_to_dict(artifact)["content_sha256"]
        ),
    )

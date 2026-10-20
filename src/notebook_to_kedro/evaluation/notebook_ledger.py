"""Exclusive draft execution reservations and offline, all-attempt accounting."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from notebook_to_kedro.evaluation.behavioral import _output, behavior_value_to_dict
from notebook_to_kedro.evaluation.behavioral_artifacts import (
    _exact_keys,
    _integer,
    _json_sha256,
    _number,
    _object,
    _string,
    _to_json,
    write_json_exclusive,
)
from notebook_to_kedro.evaluation.behavioral_execution import BehavioralExecutionConfig
from notebook_to_kedro.evaluation.notebook_artifacts import (
    _array,
    _digest,
    _limit,
    create_notebook_pipeline_artifact,
    notebook_pipeline_artifact_from_dict,
    notebook_pipeline_artifact_to_dict,
)
from notebook_to_kedro.evaluation.notebook_capture import load_notebook_body_capture
from notebook_to_kedro.evaluation.notebook_execution import (
    NotebookObservation,
    run_notebook_pipeline_capture,
)
from notebook_to_kedro.evaluation.notebook_sources import _reject_constant, _required_string
from notebook_to_kedro.generation.code.serialization import _unique_object

if TYPE_CHECKING:
    from collections.abc import Sequence

    from notebook_to_kedro.evaluation.behavioral import ExpectedBehaviorOutput
    from notebook_to_kedro.evaluation.notebook_artifacts import NotebookPipelineArtifact
    from notebook_to_kedro.evaluation.notebook_capture import NotebookBodyCapture
    from notebook_to_kedro.evaluation.notebook_sources import NotebookSourceBinding

NOTEBOOK_EXECUTION_LEDGER_VERSION = "notebook-execution-ledger-draft-1"
DEFAULT_NOTEBOOK_LEDGER_FILE_BYTES = 67_108_864
DEFAULT_NOTEBOOK_LEDGER_ATTEMPTS = 1_000
_SHA256_HEX_LENGTH = 64


@dataclass(frozen=True, slots=True)
class NotebookPipelineAttempt:
    """An immutable reservation, possibly without a durably published outcome."""

    attempt_id: str
    reserved_at: str
    reservation_sha256: str
    artifact: NotebookPipelineArtifact | None

    @property
    def status(self) -> str:
        """Do not confuse missing publication with an observed timeout or crash."""
        if self.artifact is None:
            return "unfinished"
        execution = self.artifact.run.execution
        if execution is None:
            return "static_rejected"
        if execution.status == "success":
            return self.artifact.comparison.status
        return execution.status


@dataclass(frozen=True, slots=True)
class NotebookExecutionLedger:
    """One frozen draft capture/configuration and every observed reservation."""

    manifest_sha256: str
    capture_sha256: str
    observations: tuple[NotebookObservation, ...]
    expectations: tuple[ExpectedBehaviorOutput, ...]
    configuration: BehavioralExecutionConfig
    attempts: tuple[NotebookPipelineAttempt, ...]


def _sealed(payload: dict[str, object]) -> dict[str, object]:
    normalized = _object(json.loads(_to_json(payload)), "ledger")
    return {**normalized, "content_sha256": _json_sha256(normalized)}


def _write(path: Path, payload: dict[str, object], limit: int) -> None:
    if len(_to_json(payload).encode("utf-8")) > limit:
        raise ValueError("ledger file exceeds max_file_bytes")
    write_json_exclusive(path, payload)


def _read(root: Path, path: Path, limit: int) -> dict[str, object]:
    if not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError("ledger file must be regular and contained in its directory")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("ledger file exceeds max_file_bytes")
    data = _object(
        json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant), "ledger"
    )
    if _digest(data.get("content_sha256"), "content_sha256") != _json_sha256(
        {key: value for key, value in data.items() if key != "content_sha256"}
    ):
        raise ValueError("ledger integrity mismatch")
    return data


def _manifest(
    capture: NotebookBodyCapture,
    observations: Sequence[NotebookObservation],
    expectations: Sequence[ExpectedBehaviorOutput],
    configuration: BehavioralExecutionConfig,
) -> dict[str, object]:
    names = tuple(item.dataset for item in observations)
    produced = {name for task in capture.binding.plan.task_candidates for name in task.outputs}
    if not names or len(set(names)) != len(names) or not set(names) <= produced:
        raise ValueError("ledger observations require unique planned outputs")
    if tuple(item.output_name for item in expectations) != names:
        raise ValueError("ledger expectations must exactly match observations in order")
    return _sealed(
        {
            "schema_version": NOTEBOOK_EXECUTION_LEDGER_VERSION,
            "binding_sha256": capture.binding.content_sha256,
            "capture_sha256": capture.content_sha256,
            "observations": [asdict(item) for item in observations],
            "expectations": [
                {
                    "output_name": item.output_name,
                    "value": behavior_value_to_dict(item.value),
                    "comparison": asdict(item.comparison),
                }
                for item in expectations
            ],
            "configuration": {
                **asdict(configuration),
                "timeout_seconds": float(configuration.timeout_seconds),
            },
        }
    )


def _settings(data: object) -> BehavioralExecutionConfig:
    config = _object(data, "configuration")
    _exact_keys(config, frozenset(BehavioralExecutionConfig.__dataclass_fields__), "configuration")
    return BehavioralExecutionConfig(
        _number(config["timeout_seconds"], "timeout_seconds"),
        *(
            _integer(config[name], name)
            for name in ("max_request_bytes", "max_result_bytes", "max_capture_bytes")
        ),
    )


def _targets(data: object) -> tuple[NotebookObservation, ...]:
    targets = []
    for item in _array(data, "observations"):
        row = _object(item, "observation")
        _exact_keys(row, frozenset({"dataset", "kind"}), "observation")
        targets.append(
            NotebookObservation(
                _string(row["dataset"], "dataset"),
                cast("Literal['value', 'series', 'decision_tree']", _string(row["kind"], "kind")),
            )
        )
    return tuple(targets)


def create_notebook_execution_ledger(  # noqa: PLR0913
    directory: str | Path,
    binding: NotebookSourceBinding,
    capture_directory: str | Path,
    observations: Sequence[NotebookObservation],
    expectations: Sequence[ExpectedBehaviorOutput],
    *,
    project_root: str | Path,
    config: BehavioralExecutionConfig | None = None,
    max_file_bytes: int = DEFAULT_NOTEBOOK_LEDGER_FILE_BYTES,
) -> Path:
    """Freeze one draft execution setup without static validation or worker/model I/O."""
    _limit(max_file_bytes)
    capture = load_notebook_body_capture(capture_directory, binding, project_root=project_root)
    settings = _settings(
        asdict(
            config
            or BehavioralExecutionConfig(
                timeout_seconds=60, max_request_bytes=16_777_216, max_result_bytes=4_194_304
            )
        )
    )
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
    payload = _manifest(
        capture, _targets([asdict(item) for item in observations]), expected, settings
    )
    if len(_to_json(payload).encode("utf-8")) > max_file_bytes:
        raise ValueError("ledger file exceeds max_file_bytes")
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "attempts").mkdir()
    (root / "results").mkdir()
    _write(root / "manifest.json", payload, max_file_bytes)
    return root


def _inventory(root: Path, folder: str, max_attempts: int) -> dict[str, Path]:
    directory = root / folder
    if (
        directory.is_symlink()
        or not directory.is_dir()
        or not directory.resolve().is_relative_to(root)
    ):
        raise ValueError("ledger inventory requires local directories")
    paths: dict[str, Path] = {}
    for path in directory.iterdir():
        if len(paths) >= max_attempts:
            raise ValueError("ledger inventory exceeds max_attempts")
        if path.suffix != ".json" or len(path.stem) != _SHA256_HEX_LENGTH:
            raise ValueError("unexpected ledger inventory entry")
        _digest(path.stem, "attempt filename")
        paths[path.name] = path
    return paths


def _filename(attempt_id: str) -> str:
    return (
        hashlib.sha256(_required_string(attempt_id, "attempt_id").encode("utf-8")).hexdigest()
        + ".json"
    )


def load_notebook_execution_ledger(  # noqa: PLR0913
    directory: str | Path,
    binding: NotebookSourceBinding,
    capture_directory: str | Path,
    *,
    project_root: str | Path,
    max_file_bytes: int = DEFAULT_NOTEBOOK_LEDGER_FILE_BYTES,
    max_attempts: int = DEFAULT_NOTEBOOK_LEDGER_ATTEMPTS,
) -> NotebookExecutionLedger:
    """Inspect every reservation and reverify published results without executing anything."""
    _limit(max_file_bytes)
    if _integer(max_attempts, "max_attempts") <= 0:
        raise ValueError("max_attempts must be positive")
    root = Path(directory).resolve()
    if {path.name for path in root.iterdir()} != {"manifest.json", "attempts", "results"}:
        raise ValueError("unexpected ledger directory layout")
    manifest = _read(root, root / "manifest.json", max_file_bytes)
    _exact_keys(
        manifest,
        frozenset(
            {
                "schema_version",
                "binding_sha256",
                "capture_sha256",
                "observations",
                "expectations",
                "configuration",
                "content_sha256",
            }
        ),
        "manifest",
    )
    capture = load_notebook_body_capture(capture_directory, binding, project_root=project_root)
    observations = _targets(manifest["observations"])
    expectations = tuple(_output(item) for item in _array(manifest["expectations"], "expectations"))
    settings = _settings(manifest["configuration"])
    if manifest != _manifest(capture, observations, expectations, settings):
        raise ValueError("ledger requires its exact version, sources, capture and configuration")
    reservations = _inventory(root, "attempts", max_attempts)
    results = _inventory(root, "results", max_attempts)
    if not results.keys() <= reservations.keys():
        raise ValueError("ledger result requires a reservation")
    attempts = []
    for name, path in sorted(reservations.items()):
        row = _read(root, path, max_file_bytes)
        _exact_keys(
            row,
            frozenset({"manifest_sha256", "attempt_id", "reserved_at", "content_sha256"}),
            "reservation",
        )
        identifier = _required_string(row["attempt_id"], "attempt_id")
        date = _string(row["reserved_at"], "reserved_at")
        timestamp = datetime.fromisoformat(date)
        if timestamp.tzinfo != UTC or timestamp.isoformat() != date:
            raise ValueError("reservation requires a canonical UTC timestamp")
        if row["manifest_sha256"] != manifest["content_sha256"] or _filename(identifier) != name:
            raise ValueError("ledger reservation identity mismatch")
        artifact = None
        if name in results:
            result = _read(root, results[name], max_file_bytes)
            _exact_keys(
                result, frozenset({"reservation_sha256", "artifact", "content_sha256"}), "result"
            )
            if result["reservation_sha256"] != row["content_sha256"]:
                raise ValueError("ledger result reservation mismatch")
            artifact = notebook_pipeline_artifact_from_dict(
                result["artifact"], binding, capture_directory, project_root=project_root
            )
            if (
                artifact.source_artifact_sha256 is not None
                or _manifest(
                    artifact.run.capture,
                    artifact.run.observations,
                    artifact.expectations,
                    artifact.run.configuration,
                )
                != manifest
            ):
                raise ValueError("ledger result does not match frozen execution setup")
        attempts.append(
            NotebookPipelineAttempt(
                identifier, date, _digest(row["content_sha256"], "reservation_sha256"), artifact
            )
        )
    return NotebookExecutionLedger(
        _digest(manifest["content_sha256"], "manifest_sha256"),
        capture.content_sha256,
        observations,
        expectations,
        settings,
        tuple(attempts),
    )


def reserve_notebook_pipeline_attempt(
    directory: str | Path,
    binding: NotebookSourceBinding,
    capture_directory: str | Path,
    attempt_id: str,
    *,
    project_root: str | Path,
) -> NotebookPipelineAttempt:
    """Reserve once before execution; an unfinished identifier can never be resumed or reused."""
    ledger = load_notebook_execution_ledger(
        directory, binding, capture_directory, project_root=project_root
    )
    if len(ledger.attempts) >= DEFAULT_NOTEBOOK_LEDGER_ATTEMPTS:
        raise ValueError("ledger inventory exceeds max_attempts")
    payload = _sealed(
        {
            "manifest_sha256": ledger.manifest_sha256,
            "attempt_id": _required_string(attempt_id, "attempt_id"),
            "reserved_at": datetime.now(UTC).isoformat(),
        }
    )
    _write(
        Path(directory).resolve() / "attempts" / _filename(attempt_id),
        payload,
        DEFAULT_NOTEBOOK_LEDGER_FILE_BYTES,
    )
    return NotebookPipelineAttempt(
        attempt_id,
        cast("str", payload["reserved_at"]),
        cast("str", payload["content_sha256"]),
        None,
    )


def run_notebook_pipeline_attempt(  # noqa: PLR0913
    directory: str | Path,
    binding: NotebookSourceBinding,
    capture_directory: str | Path,
    attempt_id: str,
    *,
    project_root: str | Path,
    allow_untrusted_code_execution: bool = False,
) -> NotebookPipelineAttempt:
    """Reserve, execute at most once and publish; exceptions leave an unfinished reservation."""
    if allow_untrusted_code_execution is not True:
        raise ValueError(
            "ledger execution requires allow_untrusted_code_execution=True; "
            "subprocess is not an OS sandbox"
        )
    attempt = reserve_notebook_pipeline_attempt(
        directory, binding, capture_directory, attempt_id, project_root=project_root
    )
    ledger = load_notebook_execution_ledger(
        directory, binding, capture_directory, project_root=project_root
    )
    if attempt not in ledger.attempts:
        raise ValueError("ledger reservation changed before execution")
    run = run_notebook_pipeline_capture(
        capture_directory,
        binding,
        ledger.observations,
        project_root=project_root,
        config=ledger.configuration,
        expected_capture_sha256=ledger.capture_sha256,
        allow_untrusted_code_execution=True,
    )
    artifact = create_notebook_pipeline_artifact(run, ledger.expectations)
    if (
        _manifest(run.capture, run.observations, artifact.expectations, run.configuration)
        != _manifest(run.capture, ledger.observations, ledger.expectations, ledger.configuration)
        or run.capture.content_sha256 != ledger.capture_sha256
    ):
        raise ValueError("ledger worker returned a different execution setup")
    payload = _sealed(
        {
            "reservation_sha256": attempt.reservation_sha256,
            "artifact": notebook_pipeline_artifact_to_dict(artifact),
        }
    )
    # A changed reservation/source or another publisher must not silently replace evidence.
    current = load_notebook_execution_ledger(
        directory, binding, capture_directory, project_root=project_root
    )
    if current.manifest_sha256 != ledger.manifest_sha256 or attempt not in current.attempts:
        raise ValueError("ledger reservation changed before result publication")
    _write(
        Path(directory).resolve() / "results" / _filename(attempt_id),
        payload,
        DEFAULT_NOTEBOOK_LEDGER_FILE_BYTES,
    )
    return NotebookPipelineAttempt(
        attempt.attempt_id, attempt.reserved_at, attempt.reservation_sha256, artifact
    )


def notebook_execution_ledger_summary(ledger: NotebookExecutionLedger) -> dict[str, object]:
    """Count all reservations, including unfinished ones; never report a model-accuracy score."""
    counts: dict[str, int] = {}
    for attempt in ledger.attempts:
        counts[attempt.status] = counts.get(attempt.status, 0) + 1
    unfinished = counts.get("unfinished", 0)
    return {
        "schema_version": NOTEBOOK_EXECUTION_LEDGER_VERSION,
        "manifest_sha256": ledger.manifest_sha256,
        "capture_sha256": ledger.capture_sha256,
        "total_reserved": len(ledger.attempts),
        "published": len(ledger.attempts) - unfinished,
        "unfinished": unfinished,
        "status_counts": counts,
        "attempts": [
            {
                "attempt_id": attempt.attempt_id,
                "reserved_at": attempt.reserved_at,
                "reservation_sha256": attempt.reservation_sha256,
                "status": attempt.status,
            }
            for attempt in ledger.attempts
        ],
    }

"""Opt-in operation timings and explicitly declared conversion effort comparisons."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import platform
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from notebook_to_kedro.exceptions import LocalOperationError
from notebook_to_kedro.generation.writer import write_project
from notebook_to_kedro.operations.contracts import (
    GenerateRequest,
    InspectionResult,
    InspectRequest,
    PlanningResult,
    PlanRequest,
)
from notebook_to_kedro.operations.service import run_local_operation

if TYPE_CHECKING:
    from notebook_to_kedro.operations.contracts import (
        GenerationResult,
    )

_MAX_JSON = 1_048_576
_NS_PER_SECOND = 1_000_000_000
_MAX_TEXT = 4096
_MAX_SEGMENTS = 1000
_LOGGER = logging.getLogger(__name__)
_SOURCE_SHA = re.compile(r"[0-9a-f]{64}")


def _require(condition: object, message: str) -> None:
    if not condition:
        raise LocalOperationError("LM001", message)


def _digest(data: object) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _identity(path: Path) -> dict[str, object] | None:
    try:
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        return {"sha256": digest, "size_bytes": path.stat().st_size}
    except OSError:
        return None


def _overlaps(left: Path, right: Path) -> bool:
    return left.is_relative_to(right) or right.is_relative_to(left)


def _target(request: InspectRequest | PlanRequest | GenerateRequest, directory: Path) -> Path:
    target = directory.absolute()
    config = request.configuration
    protected = [
        config.source,
        config.workflow_configuration,
        config.architecture_profile,
        config.regression_contract,
    ]
    protected.extend(
        parent
        for parent in config.source.parents
        if parent.is_relative_to(config.project_root) and (parent / "__init__.py").is_file()
    )
    if isinstance(request, GenerateRequest):
        protected.append(request.destination)
    _require(
        not any(
            _overlaps(target.resolve(), path.resolve()) for path in protected if path is not None
        ),
        "Measurement destination overlaps source, settings, package or generated destination",
    )
    return target


def measure_local_operation(
    request: InspectRequest | PlanRequest | GenerateRequest,
    directory: Path,
    *,
    case_id: str,
) -> InspectionResult | PlanningResult | GenerationResult:
    """Reserve a new attempt and time the existing operation without changing its result."""
    _require(
        isinstance(case_id, str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", case_id) is not None,
        "case_id must be a public identifier of at most 64 characters",
    )
    _require(
        isinstance(request, (InspectRequest, PlanRequest, GenerateRequest)),
        "Unsupported measured request",
    )
    target = _target(request, directory)
    operation = (
        "inspect"
        if isinstance(request, InspectRequest)
        else "plan"
        if isinstance(request, PlanRequest)
        else "generate"
    )
    reservation = {
        "schema_version": "1.0",
        "kind": "local_operation_measurement",
        "case_id": case_id,
        "operation": operation,
        "configuration": request.configuration.to_dict(),
        "source_before": _identity(request.configuration.source),
        "created_at_utc": datetime.now(UTC).isoformat(),
        "environment": {"python": platform.python_version(), "platform": sys.platform},
    }
    write_project(
        target, {Path("reservation.json"): json.dumps(reservation, sort_keys=True, indent=2) + "\n"}
    )
    status, diagnostic, active_error = "failed", None, None
    started = time.perf_counter_ns()
    try:
        try:
            result = run_local_operation(request)
        finally:
            duration = time.perf_counter_ns() - started
        status = (
            result.status
            if isinstance(result, InspectionResult)
            else "planned"
            if isinstance(result, PlanningResult)
            else "generated"
        )
        return result
    except BaseException as error:
        active_error = error
        status = "failed" if isinstance(error, Exception) else "interrupted"
        diagnostic = {
            "type": type(error).__name__,
            "message": str(error)[:4096],
            "code": getattr(error, "code", None),
        }
        raise
    finally:
        observation = {
            "schema_version": "1.0",
            "reservation_sha256": _digest(reservation),
            "status": status,
            "duration_ns": duration,
            "timing_scope": "run_local_operation_only",
            "finished_at_utc": datetime.now(UTC).isoformat(),
            "source_after": _identity(request.configuration.source),
            "diagnostic": diagnostic,
        }
        try:
            with (target / "measurement.json").open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(
                    json.dumps(observation, sort_keys=True, indent=2, allow_nan=False) + "\n"
                )
        except OSError as error:
            message = (
                "Operation already finished; cannot publish measurement. "
                "Keep the reservation and do not rerun generation blindly."
            )
            if active_error is None:
                raise LocalOperationError("LM002", message) from error
            active_error.add_note(message)
            _LOGGER.warning("%s %s", message, error)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate measurement JSON key")
        result[key] = value
    return result


def load_effort_declaration(path: str | Path) -> dict[str, Any]:
    """Read bounded strict JSON; validation is shared with direct dictionary callers."""
    location = Path(path)
    try:
        _require(
            location.is_file() and not location.is_symlink(),
            "Expected a regular measurement JSON file",
        )
        with location.open("rb") as stream:
            raw = stream.read(_MAX_JSON + 1)
        _require(len(raw) <= _MAX_JSON, "Measurement JSON exceeds 1 MiB")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
        _require(isinstance(data, dict), "Measurement JSON must be an object")
        json.dumps(data, allow_nan=False)
        return data  # type: ignore[no-any-return]
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        if isinstance(error, LocalOperationError):
            raise
        raise LocalOperationError("LM001", f"Cannot read measurement JSON: {location}") from error


def _seconds(value: object) -> float:
    _require(type(value) in (int, float), "Durations must be finite nonnegative numbers")
    try:
        result = float(value)  # type: ignore[arg-type]
    except OverflowError as error:
        raise LocalOperationError("LM001", "Duration overflows floating-point seconds") from error
    _require(math.isfinite(result) and result >= 0, "Durations must be finite nonnegative numbers")
    return result


def _effort(data: dict[str, Any], *, assisted: bool) -> dict[str, Any]:
    required = {
        "schema_version",
        "case_id",
        "source_sha256",
        "acceptance_criteria",
        "setup_mode",
        "method",
        "basis",
        "outcome",
        "operator",
        "segments",
    }
    optional = {"elapsed_seconds", "attempts_sha256"}
    _require(
        isinstance(data, dict) and required <= data.keys() <= required | optional,
        "Effort declaration has missing or unknown fields",
    )
    _require(
        data["schema_version"] == "1.0"
        and data["basis"] in ("measured", "estimated")
        and data["outcome"] in ("accepted", "in_progress", "blocked", "abandoned")
        and data["setup_mode"] in ("first_use", "reuse"),
        "Unsupported effort declaration",
    )
    _require(
        data["method"] in (("tool",) if assisted else ("manual", "general_assistant")),
        "Invalid comparison method",
    )
    _require(
        all(
            isinstance(data[key], str) and 0 < len(data[key].strip()) <= _MAX_TEXT
            for key in ("case_id", "acceptance_criteria", "operator")
        ),
        "Effort identifiers must be nonempty strings",
    )
    _require(
        isinstance(data["source_sha256"], str)
        and _SOURCE_SHA.fullmatch(data["source_sha256"]) is not None,
        "Effort declaration requires a source SHA-256",
    )
    _require(
        isinstance(data["segments"], list) and len(data["segments"]) <= _MAX_SEGMENTS,
        "Effort requires at most 1000 segments",
    )
    seconds = 0.0
    for segment in data["segments"]:
        _require(
            isinstance(segment, dict)
            and set(segment) == {"activity", "seconds"}
            and segment["activity"]
            in ("configuration", "adaptation", "correction", "review", "other"),
            "Invalid human effort segment",
        )
        seconds += _seconds(segment["seconds"])
    _require(math.isfinite(seconds), "Human effort total overflows")
    if "attempts_sha256" in data:
        _require(
            isinstance(data["attempts_sha256"], str)
            and _SOURCE_SHA.fullmatch(data["attempts_sha256"]) is not None,
            "Invalid attempt inventory SHA-256",
        )
    result: dict[str, Any] = json.loads(json.dumps(data, allow_nan=False))
    result["human_active_seconds"] = seconds
    if "elapsed_seconds" in result:
        result["elapsed_seconds"] = _seconds(result["elapsed_seconds"])
    return result


def _attempt(directory: Path) -> dict[str, Any]:
    _require(
        directory.is_dir() and not directory.is_symlink(),
        "Measurement ledger must contain only regular attempt directories",
    )
    reservation = load_effort_declaration(directory / "reservation.json")
    _require(
        reservation.get("schema_version") == "1.0"
        and reservation.get("kind") == "local_operation_measurement"
        and reservation.get("operation") in ("inspect", "plan", "generate"),
        "Invalid measurement reservation",
    )
    _require(
        isinstance(reservation.get("case_id"), str)
        and re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", reservation["case_id"]) is not None,
        "Invalid measurement case identifier",
    )
    observation_path = directory / "measurement.json"
    observation = (
        load_effort_declaration(observation_path)
        if observation_path.exists() or observation_path.is_symlink()
        else None
    )
    if observation is not None:
        _require(
            observation.get("schema_version") == "1.0"
            and observation.get("reservation_sha256") == _digest(reservation)
            and observation.get("timing_scope") == "run_local_operation_only"
            and observation.get("status")
            in ("inspected", "blocked", "planned", "generated", "failed", "interrupted"),
            "Invalid or unbound measurement observation",
        )
        _require(
            type(observation.get("duration_ns")) is int
            and 0 <= observation["duration_ns"] <= (1 << 63) - 1,
            "Measurement duration_ns must be a nonnegative integer",
        )
    return {"attempt": directory.name, "reservation": reservation, "observation": observation}


def summarize_conversion_measurements(
    directory: str | Path,
    *,
    effort: dict[str, Any] | None = None,
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Account for every attempt; compute only explicitly labelled declared comparisons."""
    root = Path(directory)
    _require(
        root.is_dir() and not root.is_symlink(), "Measurement ledger must be a regular directory"
    )
    attempts = [_attempt(path) for path in sorted(root.iterdir())]
    _require(bool(attempts), "Measurement ledger has no attempts")
    cases = {item["reservation"]["case_id"] for item in attempts}
    _require(len(cases) == 1, "Measurement ledger mixes case identifiers")
    case_id = cases.pop()
    fingerprint = _digest(attempts)
    unfinished = sum(item["observation"] is None for item in attempts)
    per_operation = {
        operation: sum(
            item["observation"]["duration_ns"]
            for item in attempts
            if item["reservation"]["operation"] == operation and item["observation"] is not None
        )
        / _NS_PER_SECOND
        for operation in ("inspect", "plan", "generate")
    }
    source_hashes = set()
    stable_source = True
    for item in attempts:
        before = item["reservation"].get("source_before")
        after = None if item["observation"] is None else item["observation"].get("source_after")
        if (
            not isinstance(before, dict)
            or before != after
            or not isinstance(before.get("sha256"), str)
            or _SOURCE_SHA.fullmatch(before["sha256"]) is None
        ):
            stable_source = False
        else:
            source_hashes.add(before["sha256"])
    source_sha = source_hashes.pop() if stable_source and len(source_hashes) == 1 else None
    human = None if effort is None else _effort(effort, assisted=True)
    reference = None if baseline is None else _effort(baseline, assisted=False)
    if human is not None:
        _require(
            human["case_id"] == case_id and human.get("attempts_sha256") == fingerprint,
            "Human effort must bind this case and the complete current attempt inventory",
        )
    comparison: dict[str, Any] = {
        "status": "not_established",
        "human_saved_seconds": None,
        "human_saved_percent": None,
        "elapsed_saved_seconds": None,
    }
    if human is not None and reference is not None:
        _require(
            all(
                human[key] == reference[key]
                for key in ("case_id", "source_sha256", "acceptance_criteria", "setup_mode")
            ),
            "Baseline uses a different case, source, acceptance contract or setup mode",
        )
        if unfinished or source_sha is None or human["source_sha256"] != source_sha:
            comparison["reason"] = "unfinished_attempts_or_changed_source"
        elif human["outcome"] != "accepted" or reference["outcome"] != "accepted":
            comparison["reason"] = "acceptance_not_declared_for_both_methods"
        else:
            saved = reference["human_active_seconds"] - human["human_active_seconds"]
            comparison.update(
                status="operator_declared_measurement"
                if human["basis"] == reference["basis"] == "measured"
                else "operator_declared_estimate",
                human_saved_seconds=saved,
                human_saved_percent=None
                if reference["human_active_seconds"] == 0
                else 100 * saved / reference["human_active_seconds"],
            )
            _require(
                comparison["human_saved_percent"] is None
                or math.isfinite(comparison["human_saved_percent"]),
                "Comparison percentage overflows",
            )
            if "elapsed_seconds" in human and "elapsed_seconds" in reference:
                comparison["elapsed_saved_seconds"] = (
                    reference["elapsed_seconds"] - human["elapsed_seconds"]
                )
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "case_id": case_id,
        "attempts_sha256": fingerprint,
        "attempts": attempts,
        "unfinished_attempts": unfinished,
        "machine_seconds_by_operation": per_operation,
        "known_machine_seconds": sum(per_operation.values()),
        "machine_timing_complete": unfinished == 0,
        "timing_scope": "local_operations_after_configuration_loading",
        "not_automatically_measured": [
            "application_preparation",
            "configuration_loading",
            "installation",
            "runtime_validation",
            "human_effort",
            "end_to_end_elapsed_time",
        ],
        "source_sha256": source_sha,
        "human_effort": human,
        "baseline": reference,
        "comparison": comparison,
        "evidence_scope": (
            "Local observations and operator declarations; "
            "acceptance and task comparability are not authenticated."
        ),
    }
    json.dumps(result, allow_nan=False)
    return result

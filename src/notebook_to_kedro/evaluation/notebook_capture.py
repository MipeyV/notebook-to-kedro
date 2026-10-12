"""Offline, exclusive evidence capture for draft whole-notebook body requests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from notebook_to_kedro.evaluation.behavioral_artifacts import (
    _exact_keys,
    _json_sha256,
    _object,
    _optional_string,
    _to_json,
    write_json_exclusive,
)
from notebook_to_kedro.evaluation.notebook_body import (
    DEFAULT_NOTEBOOK_BODY_RESPONSE_BYTES,
    NotebookBodyRecord,
)
from notebook_to_kedro.evaluation.notebook_sources import (
    _reject_constant,
    _required_string,
    validate_source_bound_notebook_body_batch,
    verify_notebook_source_binding,
)
from notebook_to_kedro.generation.code import NODE_CODE_VALIDATOR_VERSION
from notebook_to_kedro.generation.code.serialization import _unique_object

if TYPE_CHECKING:
    from notebook_to_kedro.evaluation.notebook_sources import (
        NotebookSourceBinding,
        SourceBoundNotebookBodyReport,
    )

NOTEBOOK_BODY_CAPTURE_VERSION = "notebook-body-capture-draft-1"
DEFAULT_NOTEBOOK_CAPTURE_FILE_BYTES = 16_777_216
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "binding",
        "provider_name",
        "model_name",
        "prompt_version",
        "validator_version",
        "max_response_bytes",
    }
)
_ATTEMPT_KEYS = frozenset({"manifest_sha256", "request_id"})
_RECORD_KEYS = _ATTEMPT_KEYS | {"raw_response", "raw_response_sha256", "provider_error"}


@dataclass(frozen=True, slots=True)
class NotebookBodyCapture:
    """Verified draft inventory, not execution evidence or a scored benchmark."""

    binding: NotebookSourceBinding
    provider_name: str
    model_name: str
    prompt_version: str
    max_response_bytes: int
    attempted_request_ids: tuple[str, ...]
    records: tuple[NotebookBodyRecord, ...]
    content_sha256: str

    @property
    def missing_request_ids(self) -> tuple[str, ...]:
        """Count all missing outcomes, including reserved but unfinished requests."""
        recorded = {record.request_id for record in self.records}
        return tuple(r.request_id for r in self.binding.requests if r.request_id not in recorded)

    @property
    def unfinished_request_ids(self) -> tuple[str, ...]:
        """Identify reservations with no published response or provider error."""
        missing = set(self.missing_request_ids)
        return tuple(
            identifier for identifier in self.attempted_request_ids if identifier in missing
        )

    @property
    def complete(self) -> bool:
        """Indicate complete inventory, not successful validation or execution."""
        return not self.missing_request_ids


def _positive_limit(value: int) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError("capture byte limits must be positive integers")


def _write(path: Path, payload: dict[str, object], limit: int) -> None:
    _positive_limit(limit)
    if len(_to_json(payload).encode("utf-8")) > limit:
        raise ValueError("capture file exceeds max_file_bytes")
    write_json_exclusive(path, payload)


def _read(root: Path, path: Path, limit: int) -> dict[str, object]:
    if not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError("capture file must be regular and contained in its directory")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("capture file exceeds max_file_bytes")
    return _object(
        json.loads(data, object_pairs_hook=_unique_object, parse_constant=_reject_constant),
        "notebook capture JSON",
    )


def _binding_payload(binding: NotebookSourceBinding) -> object:
    return json.loads(_to_json(asdict(binding)))


def _filename(request_id: str) -> str:
    return hashlib.sha256(request_id.encode("utf-8")).hexdigest() + ".json"


def _raw_sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8", errors="surrogatepass")).hexdigest()


def _provider_error(value: object) -> tuple[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 2:  # noqa: PLR2004
        raise ValueError("capture provider_error must contain a code and message")
    return (
        _required_string(value[0], "provider error"),
        _required_string(value[1], "provider error"),
    )


def create_notebook_body_capture(  # noqa: PLR0913
    directory: str | Path,
    binding: NotebookSourceBinding,
    *,
    project_root: str | Path,
    provider_name: str,
    model_name: str,
    prompt_version: str,
    max_response_bytes: int = DEFAULT_NOTEBOOK_BODY_RESPONSE_BYTES,
    max_file_bytes: int = DEFAULT_NOTEBOOK_CAPTURE_FILE_BYTES,
) -> Path:
    """Publish a new draft manifest; never call a model or approve pending review."""
    _positive_limit(max_response_bytes)
    _positive_limit(max_file_bytes)
    verify_notebook_source_binding(binding, project_root=project_root)
    manifest: dict[str, object] = {
        "schema_version": NOTEBOOK_BODY_CAPTURE_VERSION,
        "binding": _binding_payload(binding),
        "provider_name": _required_string(provider_name, "provider_name"),
        "model_name": _required_string(model_name, "model_name"),
        "prompt_version": _required_string(prompt_version, "prompt_version"),
        "validator_version": NODE_CODE_VALIDATOR_VERSION,
        "max_response_bytes": max_response_bytes,
    }
    if len(_to_json(manifest).encode("utf-8")) > max_file_bytes:
        raise ValueError("capture file exceeds max_file_bytes")
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "attempts").mkdir()
    (root / "responses").mkdir()
    _write(root / "manifest.json", manifest, max_file_bytes)
    return root


def _inventory(root: Path, folder: str, expected: dict[str, str]) -> tuple[Path, ...]:
    directory = root / folder
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("capture inventory requires local attempts and responses directories")
    paths = tuple(sorted(directory.iterdir()))
    if any(path.name not in expected for path in paths):
        raise ValueError("unexpected capture inventory entry")
    return paths


def load_notebook_body_capture(
    directory: str | Path,
    binding: NotebookSourceBinding,
    *,
    project_root: str | Path,
    max_file_bytes: int = DEFAULT_NOTEBOOK_CAPTURE_FILE_BYTES,
) -> NotebookBodyCapture:
    """Verify all evidence and current sources without parsing or executing proposed code."""
    _positive_limit(max_file_bytes)
    verify_notebook_source_binding(binding, project_root=project_root)
    root = Path(directory).resolve()
    if {path.name for path in root.iterdir()} != {"manifest.json", "attempts", "responses"}:
        raise ValueError("unexpected capture directory layout")
    manifest = _read(root, root / "manifest.json", max_file_bytes)
    _exact_keys(manifest, _MANIFEST_KEYS, "notebook capture manifest")
    if (
        manifest["schema_version"] != NOTEBOOK_BODY_CAPTURE_VERSION
        or manifest["validator_version"] != NODE_CODE_VALIDATOR_VERSION
        or _json_sha256({"binding": manifest["binding"]})
        != _json_sha256({"binding": _binding_payload(binding)})
    ):
        raise ValueError("capture requires its exact draft binding and validation policy")
    provider = _required_string(manifest["provider_name"], "provider_name")
    model = _required_string(manifest["model_name"], "model_name")
    prompt = _required_string(manifest["prompt_version"], "prompt_version")
    limit = manifest["max_response_bytes"]
    if type(limit) is not int:
        raise ValueError("capture byte limits must be positive integers")
    _positive_limit(limit)
    digest = _json_sha256(manifest)
    expected = {_filename(request.request_id): request.request_id for request in binding.requests}
    attempts = {}
    for path in _inventory(root, "attempts", expected):
        row = _read(root, path, max_file_bytes)
        _exact_keys(row, _ATTEMPT_KEYS, "notebook capture attempt")
        if row != {"manifest_sha256": digest, "request_id": expected[path.name]}:
            raise ValueError("capture attempt identity mismatch")
        attempts[expected[path.name]] = row
    records = {}
    for path in _inventory(root, "responses", expected):
        row = _read(root, path, max_file_bytes)
        _exact_keys(row, _RECORD_KEYS, "notebook capture response")
        identifier = expected[path.name]
        if identifier not in attempts or any(
            row[key] != attempts[identifier][key] for key in _ATTEMPT_KEYS
        ):
            raise ValueError("capture response requires its exact reservation")
        record = NotebookBodyRecord(
            identifier,
            raw_response=_optional_string(row["raw_response"], "raw_response"),
            provider_error=_provider_error(row["provider_error"]),
        )
        raw = record.raw_response
        raw_digest = None if raw is None else _raw_sha256(raw)
        if row["raw_response_sha256"] != raw_digest:
            raise ValueError("capture raw response digest mismatch")
        records[identifier] = record
    ordered_attempts = tuple(r.request_id for r in binding.requests if r.request_id in attempts)
    ordered_records = tuple(
        records[r.request_id] for r in binding.requests if r.request_id in records
    )
    return NotebookBodyCapture(
        binding,
        provider,
        model,
        prompt,
        limit,
        ordered_attempts,
        ordered_records,
        _json_sha256(
            {
                "manifest": manifest,
                "attempts": attempts,
                "records": [asdict(record) for record in ordered_records],
            }
        ),
    )


def reserve_notebook_body_request(
    directory: str | Path,
    binding: NotebookSourceBinding,
    request_id: str,
    *,
    project_root: str | Path,
    max_file_bytes: int = DEFAULT_NOTEBOOK_CAPTURE_FILE_BYTES,
) -> None:
    """Exclusively reserve one frozen request; no automatic call, retry or resume."""
    load_notebook_body_capture(
        directory, binding, project_root=project_root, max_file_bytes=max_file_bytes
    )
    if request_id not in {r.request_id for r in binding.requests}:
        raise ValueError("unknown notebook capture request_id")
    root = Path(directory).resolve()
    digest = _json_sha256(_read(root, root / "manifest.json", max_file_bytes))
    _write(
        root / "attempts" / _filename(request_id),
        {"manifest_sha256": digest, "request_id": request_id},
        max_file_bytes,
    )


def record_notebook_body_response(
    directory: str | Path,
    binding: NotebookSourceBinding,
    record: NotebookBodyRecord,
    *,
    project_root: str | Path,
    max_file_bytes: int = DEFAULT_NOTEBOOK_CAPTURE_FILE_BYTES,
) -> None:
    """Publish an exact reserved outcome before any proposal parsing or validation."""
    capture = load_notebook_body_capture(
        directory, binding, project_root=project_root, max_file_bytes=max_file_bytes
    )
    if record.request_id not in capture.attempted_request_ids:
        raise ValueError("capture response requires a reservation")
    root = Path(directory).resolve()
    digest = _json_sha256(_read(root, root / "manifest.json", max_file_bytes))
    raw = record.raw_response
    _write(
        root / "responses" / _filename(record.request_id),
        {
            "manifest_sha256": digest,
            "request_id": record.request_id,
            "raw_response": raw,
            "raw_response_sha256": None if raw is None else _raw_sha256(raw),
            "provider_error": record.provider_error,
        },
        max_file_bytes,
    )


def replay_notebook_body_capture(
    directory: str | Path,
    binding: NotebookSourceBinding,
    *,
    project_root: str | Path,
    max_file_bytes: int = DEFAULT_NOTEBOOK_CAPTURE_FILE_BYTES,
) -> SourceBoundNotebookBodyReport:
    """Revalidate saved raw outcomes offline, retaining every missing planned slot."""
    capture = load_notebook_body_capture(
        directory, binding, project_root=project_root, max_file_bytes=max_file_bytes
    )
    return validate_source_bound_notebook_body_batch(
        binding,
        capture.records,
        project_root=project_root,
        max_response_bytes=capture.max_response_bytes,
    )

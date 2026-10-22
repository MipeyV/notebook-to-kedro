"""Opt-in metadata-only Ollama controls and offline identity compatibility checks."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from notebook_to_kedro.evaluation.behavioral_artifacts import (
    _exact_keys,
    _integer,
    _json_sha256,
    _number,
    _object,
    _ollama_model_identity,
    _optional_string,
    _to_json,
    write_json_exclusive,
)
from notebook_to_kedro.evaluation.notebook_artifacts import _array, _digest, _limit
from notebook_to_kedro.evaluation.notebook_sources import _reject_constant, _required_string
from notebook_to_kedro.generation.code.serialization import _unique_object
from notebook_to_kedro.semantic.ollama import _looks_like_cloud_model, _normalize_local_base_url

if TYPE_CHECKING:
    from collections.abc import Sequence

NOTEBOOK_OLLAMA_CONTROLS_VERSION = "notebook-ollama-controls-draft-1"
DEFAULT_OLLAMA_METADATA_BYTES = 1_000_000
DEFAULT_OLLAMA_CONTROLS_BYTES = 33_554_432
_ROLES = ("version_before", "tags_before", "show", "version_after", "tags_after")


@dataclass(frozen=True, slots=True)
class NotebookOllamaSettings:
    """Selected requested options, never measured or applied by metadata collection."""

    temperature: float = 0.0
    seed: int | None = None
    num_ctx: int | None = None
    num_predict: int | None = None

    def __post_init__(self) -> None:
        value = _number(self.temperature, "temperature")
        if not math.isfinite(value) or value < 0:
            raise ValueError("temperature must be finite and nonnegative")
        for name in ("seed", "num_ctx", "num_predict"):
            item = getattr(self, name)
            if item is not None and _integer(item, name) < (0 if name == "seed" else 1):
                raise ValueError(
                    f"{name} must be {'nonnegative' if name == 'seed' else 'positive'}"
                )

    def to_options(self) -> dict[str, object]:
        """Omit unspecified values without inventing server defaults."""
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True, slots=True)
class NotebookOllamaResponse:
    """One exact UTF-8 JSON response from a fixed metadata endpoint role."""

    role: str
    raw_response: str


@dataclass(frozen=True, slots=True)
class NotebookOllamaControls:
    """An integrity-bound metadata sample, not human approval or execution attestation."""

    schema_version: str
    base_url: str
    model_name: str
    requested: NotebookOllamaSettings
    responses: tuple[NotebookOllamaResponse, ...]
    max_response_bytes: int
    version_before: str | None
    version_after: str | None
    digest_before: str | None
    digest_after: str | None
    target_before_sha256: str
    target_after_sha256: str
    show_sha256: str
    advertised_parameters: str | None
    advertised_context_length: int | None
    effective_options: None
    effective_context_length: None
    content_sha256: str


def _base_url(value: str) -> str:
    base = _normalize_local_base_url(value)
    parsed = urlsplit(base)
    if parsed.hostname == "localhost":
        # Avoid DNS and environment proxy routing for the new metadata-only collector.
        return "http://127.0.0.1" + ("" if parsed.port is None else f":{parsed.port}")
    return base


def _model_name(value: object) -> str:
    name = _required_string(value, "model_name")
    if name != name.strip() or _looks_like_cloud_model(name.lower()):
        raise ValueError("model_name must identify an exact local model, not a cloud tag")
    return name


def _json_object(raw: str, limit: int) -> dict[str, object]:
    if len(raw.encode("utf-8")) > limit:
        raise ValueError("Ollama metadata exceeds max_response_bytes")
    data = _object(
        json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant),
        "Ollama metadata",
    )
    if "error" in data:
        raise ValueError("Ollama metadata reports an error")
    _remote_check(data)
    return data


def _remote_check(data: dict[str, object]) -> None:
    for name in ("remote_model", "remote_host"):
        if name in data and data[name] != "":
            raise ValueError("remote or ambiguous Ollama model metadata is not supported")


def _identity(
    version: dict[str, object], tags: dict[str, object], model_name: str
) -> tuple[str | None, str | None, str]:
    selected = []
    for item in _array(tags.get("models", []), "models"):
        row = _object(item, "Ollama model")
        if model_name in (row.get("name"), row.get("model")):
            if any(row[key] != model_name for key in ("name", "model") if key in row):
                raise ValueError("Ollama model aliases disagree")
            _remote_check(row)
            selected.append(row)
    if len(selected) > 1:
        raise ValueError("Ollama model identity is ambiguous")
    row = selected[0] if selected else {}
    server = None if "version" not in version else _required_string(version["version"], "version")
    digest = None if "digest" not in row else _digest(row["digest"], "model digest")
    if server is not None and digest is not None:
        # Share identity decoding with the existing node benchmark, not its legacy transport.
        server, digest = _ollama_model_identity(version, {"models": [row]}, model_name)
    return server, digest, _json_sha256(row)


def _settings(data: object) -> NotebookOllamaSettings:
    row = _object(data, "requested settings")
    _exact_keys(row, frozenset(NotebookOllamaSettings.__dataclass_fields__), "requested settings")
    settings = NotebookOllamaSettings(
        _number(row["temperature"], "temperature"),
        *(
            None if row[name] is None else _integer(row[name], name)
            for name in ("seed", "num_ctx", "num_predict")
        ),
    )
    return settings


def create_notebook_ollama_controls(
    model_name: str,
    responses: Sequence[NotebookOllamaResponse],
    *,
    requested: NotebookOllamaSettings | None = None,
    base_url: str = "http://127.0.0.1:11434",
    max_response_bytes: int = DEFAULT_OLLAMA_METADATA_BYTES,
) -> NotebookOllamaControls:
    """Reconstruct controls from recorded metadata without HTTP or inference I/O."""
    _limit(max_response_bytes)
    name = _model_name(model_name)
    base = _base_url(base_url)
    settings = _settings(asdict(requested or NotebookOllamaSettings()))
    records = tuple(responses)
    if tuple(item.role for item in records) != _ROLES:
        raise ValueError("Ollama metadata requires the exact ordered five-response inventory")
    version_before, tags_before, show, version_after, tags_after = (
        _json_object(item.raw_response, max_response_bytes) for item in records
    )
    first = _identity(version_before, tags_before, name)
    last = _identity(version_after, tags_after, name)
    parameters = _optional_string(show.get("parameters"), "parameters")
    info = _object(show.get("model_info", {}), "model_info")
    architecture = info.get("general.architecture")
    context = None
    if architecture is not None:
        architecture = _required_string(architecture, "architecture")
        if f"{architecture}.context_length" in info:
            context = _integer(info[f"{architecture}.context_length"], "context_length")
            if context <= 0:
                raise ValueError("context_length must be positive")
    control = NotebookOllamaControls(
        schema_version=NOTEBOOK_OLLAMA_CONTROLS_VERSION,
        base_url=base,
        model_name=name,
        requested=settings,
        responses=records,
        max_response_bytes=max_response_bytes,
        version_before=first[0],
        version_after=last[0],
        digest_before=first[1],
        digest_after=last[1],
        target_before_sha256=first[2],
        target_after_sha256=last[2],
        show_sha256=_json_sha256(show),
        advertised_parameters=parameters,
        advertised_context_length=context,
        effective_options=None,
        effective_context_length=None,
        content_sha256="",
    )
    payload = asdict(control)
    payload.pop("content_sha256")
    return replace(control, content_sha256=_json_sha256(payload))


def notebook_ollama_controls_to_dict(control: NotebookOllamaControls) -> dict[str, object]:
    """Recompute derived identities and reject mutated or forged in-memory summaries."""
    rebuilt = create_notebook_ollama_controls(
        control.model_name,
        control.responses,
        requested=control.requested,
        base_url=control.base_url,
        max_response_bytes=control.max_response_bytes,
    )
    if _json_sha256(asdict(control)) != _json_sha256(asdict(rebuilt)):
        raise ValueError("Ollama controls version, integrity or derived evidence mismatch")
    return _object(json.loads(_to_json(asdict(control))), "Ollama controls")


def notebook_ollama_controls_from_dict(payload: object) -> NotebookOllamaControls:
    """Inspect exact saved metadata and recompute every summary without contacting Ollama."""
    data = _object(payload, "Ollama controls")
    _exact_keys(data, frozenset(NotebookOllamaControls.__dataclass_fields__), "Ollama controls")
    _digest(data["content_sha256"], "content_sha256")
    records = []
    for item in _array(data["responses"], "responses"):
        row = _object(item, "response")
        _exact_keys(row, frozenset({"role", "raw_response"}), "response")
        records.append(
            NotebookOllamaResponse(
                _required_string(row["role"], "role"),
                _required_string(row["raw_response"], "raw_response"),
            )
        )
    rebuilt = create_notebook_ollama_controls(
        _model_name(data["model_name"]),
        records,
        requested=_settings(data["requested"]),
        base_url=_required_string(data["base_url"], "base_url"),
        max_response_bytes=_integer(data["max_response_bytes"], "max_response_bytes"),
    )
    if _json_sha256(data) != _json_sha256(notebook_ollama_controls_to_dict(rebuilt)):
        raise ValueError("Ollama controls integrity or derived evidence mismatch")
    return rebuilt


def write_notebook_ollama_controls(
    path: str | Path,
    control: NotebookOllamaControls,
    *,
    max_file_bytes: int = DEFAULT_OLLAMA_CONTROLS_BYTES,
) -> Path:
    """Exclusively publish a bounded metadata record without approving a campaign."""
    _limit(max_file_bytes)
    payload = notebook_ollama_controls_to_dict(control)
    if len(_to_json(payload).encode("utf-8")) > max_file_bytes:
        raise ValueError("Ollama controls exceed max_file_bytes")
    destination = Path(path)
    write_json_exclusive(destination, payload)
    return destination


def load_notebook_ollama_controls(
    path: str | Path, *, max_file_bytes: int = DEFAULT_OLLAMA_CONTROLS_BYTES
) -> NotebookOllamaControls:
    """Bound file reads and inspect offline; no service, model or notebook I/O."""
    _limit(max_file_bytes)
    source = Path(path)
    if not source.is_file():
        raise ValueError("Ollama controls require a regular file")
    with source.open("rb") as stream:
        raw = stream.read(max_file_bytes + 1)
    if len(raw) > max_file_bytes:
        raise ValueError("Ollama controls exceed max_file_bytes")
    return notebook_ollama_controls_from_dict(
        json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    )


def require_notebook_ollama_compatibility(
    before: NotebookOllamaControls, after: NotebookOllamaControls, current: NotebookOllamaControls
) -> None:
    """Require known stable identities and matching selected controls, not effective inference."""
    signatures = []
    for control in (before, after, current):
        notebook_ollama_controls_to_dict(control)
        if None in (
            control.version_before,
            control.version_after,
            control.digest_before,
            control.digest_after,
        ):
            raise ValueError("Ollama identity compatibility requires known versions and digests")
        if (control.version_before, control.digest_before, control.target_before_sha256) != (
            control.version_after,
            control.digest_after,
            control.target_after_sha256,
        ):
            raise ValueError("Ollama model identity changed during metadata collection")
        if control.requested.num_ctx is not None and (
            control.advertised_context_length is None
            or control.requested.num_ctx > control.advertised_context_length
        ):
            raise ValueError(
                "requested num_ctx requires a known sufficient advertised context length"
            )
        signatures.append(
            _json_sha256(
                {
                    "base_url": control.base_url,
                    "model_name": control.model_name,
                    "requested": asdict(control.requested),
                    "version": control.version_before,
                    "target": control.target_before_sha256,
                    "show": control.show_sha256,
                }
            )
        )
    if len(set(signatures)) != 1:
        raise ValueError("Ollama model controls compatibility mismatch")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        raise ValueError("Ollama metadata redirects are forbidden")


def _fetch_metadata(base: str, role: str, model_name: str, timeout: float, limit: int) -> str:
    route = "show" if role == "show" else "version" if role.startswith("version") else "tags"
    body = (
        _to_json({"model": model_name, "verbose": False}).encode("utf-8")
        if role == "show"
        else None
    )
    request = Request(
        f"{base}/api/{route}",
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    try:
        with build_opener(ProxyHandler({}), _NoRedirect()).open(
            request, timeout=timeout
        ) as response:
            raw: bytes = response.read(limit + 1)
    except OSError as error:
        raise ValueError("cannot collect local Ollama metadata") from error
    if len(raw) > limit:
        raise ValueError("Ollama metadata exceeds max_response_bytes")
    return raw.decode("utf-8")


def collect_notebook_ollama_controls(  # noqa: PLR0913
    model_name: str,
    *,
    allow_local_metadata_queries: bool = False,
    requested: NotebookOllamaSettings | None = None,
    base_url: str = "http://127.0.0.1:11434",
    timeout_seconds: float = 5.0,
    max_response_bytes: int = DEFAULT_OLLAMA_METADATA_BYTES,
) -> NotebookOllamaControls:
    """Opt into five metadata-only requests; never load, pull, execute or infer with a model."""
    if allow_local_metadata_queries is not True:
        raise ValueError("Ollama metadata collection requires allow_local_metadata_queries=True")
    base, name = _base_url(base_url), _model_name(model_name)
    _limit(max_response_bytes)
    timeout = _number(timeout_seconds, "timeout_seconds")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout_seconds must be positive and finite")
    settings = _settings(asdict(requested or NotebookOllamaSettings()))
    records: list[NotebookOllamaResponse] = []
    for role in _ROLES:
        raw = _fetch_metadata(base, role, name, timeout, max_response_bytes)
        data = _json_object(raw, max_response_bytes)
        if role == "tags_before":
            _identity(_json_object(records[0].raw_response, max_response_bytes), data, name)
        records.append(NotebookOllamaResponse(role, raw))
    return create_notebook_ollama_controls(
        name, records, requested=settings, base_url=base, max_response_bytes=max_response_bytes
    )

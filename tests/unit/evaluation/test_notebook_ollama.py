"""Synthetic metadata samples exercise controls without contacting any Ollama service."""

from __future__ import annotations

import json
from dataclasses import replace
from email.message import Message
from typing import TYPE_CHECKING, Any, Self
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler

import pytest

from notebook_to_kedro.evaluation import (
    NotebookOllamaResponse,
    NotebookOllamaSettings,
    collect_notebook_ollama_controls,
    create_notebook_ollama_controls,
    load_notebook_ollama_controls,
    notebook_ollama_controls_from_dict,
    notebook_ollama_controls_to_dict,
    require_notebook_ollama_compatibility,
    write_notebook_ollama_controls,
)
from notebook_to_kedro.evaluation import notebook_ollama as controls
from notebook_to_kedro.evaluation.behavioral_artifacts import _json_sha256, _to_json
from notebook_to_kedro.exceptions import BehavioralBenchmarkArtifactError

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from urllib.request import Request

MODEL = "synthetic-model:unit-test"
DIGEST = "1" * 64
ROLES = ("version_before", "tags_before", "show", "version_after", "tags_after")


def _payloads() -> dict[str, Any]:
    return {
        "version_before": {"version": "synthetic-server-1"},
        "version_after": {"version": "synthetic-server-1"},
        "tags_before": {"models": [{"name": MODEL, "model": MODEL, "digest": DIGEST}]},
        "tags_after": {"models": [{"name": MODEL, "model": MODEL, "digest": DIGEST}]},
        "show": {
            "parameters": "temperature 0\nnum_ctx 4096\n",
            "template": "synthetic",
            "model_info": {"general.architecture": "synthetic", "synthetic.context_length": 8192},
        },
    }


def _records(payloads: dict[str, Any] | None = None) -> tuple[NotebookOllamaResponse, ...]:
    data = _payloads() if payloads is None else payloads
    return tuple(NotebookOllamaResponse(role, json.dumps(data[role])) for role in ROLES)


def _control(
    payloads: dict[str, Any] | None = None, **kwargs: Any
) -> controls.NotebookOllamaControls:
    return create_notebook_ollama_controls(MODEL, _records(payloads), **kwargs)


def _resign(data: dict[str, Any]) -> dict[str, Any]:
    data["content_sha256"] = _json_sha256(
        {key: value for key, value in data.items() if key != "content_sha256"}
    )
    return data


def _no_http(*_args: object, **_kwargs: object) -> str:
    pytest.fail("offline inspection or refused consent must not perform HTTP")


def test_offline_round_trip_and_explicit_unknown_effective_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(controls, "_fetch_metadata", _no_http)
    settings = NotebookOllamaSettings(temperature=0, seed=7, num_ctx=4096, num_predict=1024)
    control = _control(requested=settings, base_url="http://localhost:11434/")
    assert control.base_url == "http://127.0.0.1:11434"
    assert control.version_before == control.version_after == "synthetic-server-1"
    assert control.digest_before == control.digest_after == DIGEST
    assert control.advertised_context_length == 8192
    assert control.advertised_parameters == "temperature 0\nnum_ctx 4096\n"
    assert control.effective_options is control.effective_context_length is None
    assert control.requested.to_options() == {
        "temperature": 0.0,
        "seed": 7,
        "num_ctx": 4096,
        "num_predict": 1024,
    }
    assert NotebookOllamaSettings().to_options() == {"temperature": 0.0}
    path = write_notebook_ollama_controls(tmp_path / "controls.json", control)
    assert load_notebook_ollama_controls(path) == control
    payload = notebook_ollama_controls_to_dict(control)
    assert notebook_ollama_controls_from_dict(payload) == control
    assert payload["effective_options"] is None
    assert payload["effective_context_length"] is None
    require_notebook_ollama_compatibility(control, control, control)
    with pytest.raises(BehavioralBenchmarkArtifactError, match="already exists"):
        write_notebook_ollama_controls(path, control)


def test_collector_uses_only_five_metadata_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    data = _payloads()

    def fetch(base: str, role: str, model: str, timeout: float, limit: int) -> str:
        calls.append((base, role, model, timeout, limit))
        return json.dumps(data[role])

    monkeypatch.setattr(controls, "_fetch_metadata", fetch)
    control = collect_notebook_ollama_controls(
        MODEL,
        allow_local_metadata_queries=True,
        base_url="http://localhost:11434",
        requested=NotebookOllamaSettings(num_ctx=4096),
        timeout_seconds=2,
        max_response_bytes=1024,
    )
    assert [item[1] for item in calls] == list(ROLES)
    assert all(
        item[0] == "http://127.0.0.1:11434" and item[2:] == (MODEL, 2.0, 1024) for item in calls
    )
    assert control == _control(
        requested=NotebookOllamaSettings(num_ctx=4096), max_response_bytes=1024
    )


@pytest.mark.parametrize("consent", [False, None, 1])
def test_collection_consent_precedes_all_io(monkeypatch: pytest.MonkeyPatch, consent: Any) -> None:
    monkeypatch.setattr(controls, "_fetch_metadata", _no_http)
    with pytest.raises(ValueError, match="allow_local_metadata_queries=True"):
        collect_notebook_ollama_controls(
            "", base_url="https://remote.invalid", allow_local_metadata_queries=consent
        )


@pytest.mark.parametrize(
    "setting",
    [
        {"temperature": True},
        {"temperature": -1},
        {"temperature": float("nan")},
        {"temperature": float("inf")},
        {"seed": -1},
        {"seed": False},
        {"num_ctx": 0},
        {"num_predict": -1},
        {"num_predict": 1.5},
    ],
)
def test_invalid_requested_settings(setting: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"temperature|seed|num_ctx|num_predict"):
        NotebookOllamaSettings(**setting)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_url": "https://127.0.0.1:11434"},
        {"base_url": "http://remote.invalid"},
        {"base_url": "http://localhost:11434/path"},
        {"timeout_seconds": 0},
        {"timeout_seconds": float("nan")},
        {"timeout_seconds": True},
        {"max_response_bytes": 0},
        {"max_response_bytes": True},
    ],
)
def test_invalid_collection_settings_stop_before_http(
    monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, Any]
) -> None:
    monkeypatch.setattr(controls, "_fetch_metadata", _no_http)
    with pytest.raises(ValueError, match=r"base_url|timeout_seconds|max_file_bytes"):
        collect_notebook_ollama_controls(MODEL, allow_local_metadata_queries=True, **kwargs)


@pytest.mark.parametrize("model", ["", " ", " model:tag", "model:CLOUD", "model:8b-cloud"])
def test_cloud_or_ambiguous_model_names_stop_before_http(
    monkeypatch: pytest.MonkeyPatch, model: str
) -> None:
    monkeypatch.setattr(controls, "_fetch_metadata", _no_http)
    with pytest.raises(ValueError, match="model_name"):
        collect_notebook_ollama_controls(model, allow_local_metadata_queries=True)


@pytest.mark.parametrize("base", ["http://localhost", "http://[::1]:11434"])
def test_local_base_normalization(base: str) -> None:
    control = _control(base_url=base)
    assert control.base_url == ("http://127.0.0.1" if base.endswith("localhost") else base)


@pytest.mark.parametrize(
    "mode",
    [
        "missing_version",
        "missing_digest",
        "missing_model",
        "missing_models",
        "missing_info",
        "missing_context",
        "missing_parameters",
        "empty_parameters",
    ],
)
def test_unknowns_remain_inspectable_not_invented(mode: str) -> None:
    data = _payloads()
    if mode == "missing_version":
        data["version_before"] = {}
    elif mode == "missing_digest":
        del data["tags_before"]["models"][0]["digest"]
    elif mode == "missing_model":
        data["tags_before"]["models"] = [{"name": "other", "digest": DIGEST}]
    elif mode == "missing_models":
        data["tags_before"] = {}
    elif mode == "missing_info":
        data["show"] = {}
    elif mode == "missing_context":
        del data["show"]["model_info"]["synthetic.context_length"]
    elif mode == "missing_parameters":
        del data["show"]["parameters"]
    else:
        data["show"]["parameters"] = ""
    control = _control(data)
    assert notebook_ollama_controls_from_dict(notebook_ollama_controls_to_dict(control)) == control
    assert control.effective_context_length is None
    if mode in ("missing_version", "missing_digest", "missing_model", "missing_models"):
        with pytest.raises(ValueError, match="known versions and digests"):
            require_notebook_ollama_compatibility(control, control, control)
    elif mode in ("missing_info", "missing_context"):
        assert control.advertised_context_length is None
        if mode == "missing_info":
            assert control.advertised_parameters is None
    else:
        assert control.advertised_parameters == (None if mode == "missing_parameters" else "")


@pytest.mark.parametrize(
    "mode",
    [
        "alias",
        "duplicate",
        "bad_digest",
        "remote_tag",
        "remote_show",
        "null_remote",
        "bad_version",
        "bad_info",
        "bad_architecture",
        "bad_context",
        "bad_parameters",
        "bad_models",
        "error",
    ],
)
def test_malformed_or_remote_metadata_is_rejected(mode: str) -> None:
    data = _payloads()
    tag = data["tags_before"]["models"][0]
    if mode == "alias":
        tag["model"] = "different"
    elif mode == "duplicate":
        data["tags_before"]["models"].append(dict(tag))
    elif mode == "bad_digest":
        tag["digest"] = "bad"
    elif mode == "remote_tag":
        tag["remote_model"] = "remote"
    elif mode == "remote_show":
        data["show"]["remote_host"] = "https://remote.invalid"
    elif mode == "null_remote":
        tag["remote_host"] = None
    elif mode == "bad_version":
        data["version_before"]["version"] = ""
    elif mode in ("bad_info", "bad_architecture"):
        data["show"]["model_info"] = [] if mode == "bad_info" else {"general.architecture": 42}
    elif mode == "bad_context":
        data["show"]["model_info"]["synthetic.context_length"] = 0
    elif mode == "bad_parameters":
        data["show"]["parameters"] = []
    elif mode == "bad_models":
        data["tags_before"]["models"] = {}
    else:
        data["show"]["error"] = "synthetic"
    with pytest.raises(
        ValueError,
        match=r"Ollama|digest|version|model_info|architecture|context_length|parameters|models",
    ):
        _control(data)


@pytest.mark.parametrize("role", ["tags_before", "show"])
def test_remote_metadata_aborts_collection_without_further_queries(
    monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    data = _payloads()
    if role == "show":
        data[role]["remote_host"] = "https://remote.invalid"
    else:
        data[role]["models"][0]["remote_model"] = "remote"
    seen = []

    def fetch(_base: str, item: str, *_args: Any) -> str:
        seen.append(item)
        return json.dumps(data[item])

    monkeypatch.setattr(controls, "_fetch_metadata", fetch)
    with pytest.raises(ValueError, match="remote"):
        collect_notebook_ollama_controls(MODEL, allow_local_metadata_queries=True)
    assert seen == list(ROLES[: ROLES.index(role) + 1])


@pytest.mark.parametrize("role", ROLES)
def test_offline_import_refuses_remote_markers_in_every_response(role: str) -> None:
    data = _payloads()
    data[role]["remote_host"] = "https://remote.invalid"
    with pytest.raises(ValueError, match="remote"):
        _control(data)


@pytest.mark.parametrize("field", ["version_after", "digest_after", "target_after"])
def test_observed_within_sample_drift_stays_inspectable_but_not_compatible(field: str) -> None:
    data = _payloads()
    if field == "version_after":
        data[field]["version"] = "changed"
    elif field == "digest_after":
        data["tags_after"]["models"][0]["digest"] = "2" * 64
    else:
        data["tags_after"]["models"][0]["size"] = 123
    control = _control(data)
    assert notebook_ollama_controls_from_dict(notebook_ollama_controls_to_dict(control)) == control
    with pytest.raises(ValueError, match="changed during"):
        require_notebook_ollama_compatibility(control, control, control)


@pytest.mark.parametrize("mode", ["model", "server", "show", "settings", "base"])
def test_separate_samples_require_matching_selected_controls(mode: str) -> None:
    data = _payloads()
    kwargs: dict[str, Any] = {}
    if mode == "model":
        for role in ("tags_before", "tags_after"):
            data[role]["models"][0]["digest"] = "2" * 64
    elif mode == "server":
        for role in ("version_before", "version_after"):
            data[role]["version"] = "changed"
    elif mode == "show":
        data["show"]["template"] = "changed"
    elif mode == "settings":
        kwargs["requested"] = NotebookOllamaSettings(seed=42)
    else:
        kwargs["base_url"] = "http://127.0.0.1:11435"
    changed = _control(data, **kwargs)
    with pytest.raises(ValueError, match="compatibility mismatch"):
        require_notebook_ollama_compatibility(_control(), _control(), changed)


def test_unrelated_inventory_and_json_whitespace_do_not_change_selected_identity() -> None:
    data = _payloads()
    data["tags_after"]["models"].append({"name": "unrelated", "digest": "2" * 64})
    changed = _control(data)
    original = _control()
    assert changed.content_sha256 != original.content_sha256
    require_notebook_ollama_compatibility(original, changed, original)
    expanded = create_notebook_ollama_controls(
        MODEL,
        tuple(
            replace(item, raw_response=json.dumps(json.loads(item.raw_response), indent=4))
            for item in original.responses
        ),
    )
    assert expanded.content_sha256 != original.content_sha256
    require_notebook_ollama_compatibility(original, expanded, original)


@pytest.mark.parametrize("unknown", [False, True])
def test_context_request_requires_sufficient_advertised_capacity(*, unknown: bool) -> None:
    data = _payloads()
    if unknown:
        data["show"] = {}
    control = _control(data, requested=NotebookOllamaSettings(num_ctx=16384))
    with pytest.raises(ValueError, match="advertised context"):
        require_notebook_ollama_compatibility(control, control, control)


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "show_sha256",
        "advertised_context_length",
        "effective_options",
        "content_sha256",
        "extra",
    ],
)
def test_rehashed_forged_summaries_are_recomputed(field: str) -> None:
    payload: dict[str, Any] = notebook_ollama_controls_to_dict(_control())
    payload[field] = (
        {}
        if field == "effective_options"
        else "bad"
        if field in ("schema_version", "show_sha256", "content_sha256")
        else 1
    )
    if field != "content_sha256":
        _resign(payload)
    with pytest.raises(ValueError, match=r"Ollama|content_sha256"):
        notebook_ollama_controls_from_dict(payload)
    with pytest.raises(ValueError, match="mismatch"):
        notebook_ollama_controls_to_dict(replace(_control(), content_sha256="0" * 64))


@pytest.mark.parametrize(
    "mode",
    ["inventory", "row_fields", "settings_fields", "duplicate", "nonfinite", "array", "oversized"],
)
def test_saved_raw_metadata_and_shapes_are_strict(mode: str) -> None:
    payload: dict[str, Any] = notebook_ollama_controls_to_dict(_control())
    if mode == "inventory":
        payload["responses"].reverse()
    elif mode == "row_fields":
        payload["responses"][0]["extra"] = 1
    elif mode == "settings_fields":
        payload["requested"]["extra"] = 1
    else:
        payload["responses"][0]["raw_response"] = {
            "duplicate": '{"x":1,"x":2}',
            "nonfinite": '{"x":NaN}',
            "array": "[]",
            "oversized": '{"x":"' + "x" * controls.DEFAULT_OLLAMA_METADATA_BYTES + '"}',
        }[mode]
    _resign(payload)
    with pytest.raises(
        ValueError, match=r"fields|inventory|duplicate|non-finite|object|max_response_bytes"
    ):
        notebook_ollama_controls_from_dict(payload)


@pytest.mark.parametrize("raw", ["{", '{"x":1,"x":2}', '{"x":NaN}', "[]"])
def test_invalid_control_files_are_rejected(tmp_path: Path, raw: str) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match=r"property name|duplicate|non-finite|object"):
        load_notebook_ollama_controls(path)


def test_control_file_limits(tmp_path: Path) -> None:
    control = _control()
    path = write_notebook_ollama_controls(tmp_path / "control.json", control)
    assert load_notebook_ollama_controls(path, max_file_bytes=path.stat().st_size) == control
    for limit in (0, True, 1):
        with pytest.raises(ValueError, match="max_file_bytes"):
            load_notebook_ollama_controls(path, max_file_bytes=limit)
        with pytest.raises(ValueError, match="max_file_bytes"):
            write_notebook_ollama_controls(tmp_path / "not-written", control, max_file_bytes=limit)
    with pytest.raises(ValueError, match="regular file"):
        load_notebook_ollama_controls(tmp_path)
    assert not (tmp_path / "not-written").exists()


class _Response:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def read(self, limit: int) -> bytes:
        return self.raw[:limit]


def _opener(monkeypatch: pytest.MonkeyPatch, handler: Callable[..., Any]) -> None:
    class Opener:
        def open(self, *args: Any, **kwargs: Any) -> Any:
            return handler(*args, **kwargs)

    def build(*handlers: object) -> Opener:
        assert isinstance(handlers[0], ProxyHandler)
        assert vars(handlers[0]).get("proxies") == {}
        assert isinstance(handlers[1], controls._NoRedirect)
        return Opener()

    monkeypatch.setattr(controls, "build_opener", build)


@pytest.mark.parametrize("role", ROLES)
def test_bounded_metadata_transport_has_no_inference_payload(
    monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    def opened(request: Request, timeout: float) -> _Response:
        assert timeout == 2
        assert request.get_method() == ("POST" if role == "show" else "GET")
        route = "show" if role == "show" else "version" if role.startswith("version") else "tags"
        assert request.full_url == f"http://127.0.0.1:11434/api/{route}"
        assert request.data == (
            _to_json({"model": MODEL, "verbose": False}).encode() if role == "show" else None
        )
        return _Response(b'{"synthetic":true}')

    _opener(monkeypatch, opened)
    assert (
        controls._fetch_metadata("http://127.0.0.1:11434", role, MODEL, 2, 1024)
        == '{"synthetic":true}'
    )


@pytest.mark.parametrize("kind", ["oversized", "utf8", "timeout", "url", "http"])
def test_transport_fails_closed(monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    def opened(*_args: Any, **_kwargs: Any) -> _Response:
        if kind == "oversized":
            return _Response(b"x" * 100)
        if kind == "utf8":
            return _Response(b"\xff")
        if kind == "timeout":
            raise TimeoutError("synthetic")
        if kind == "url":
            raise URLError("synthetic")
        raise HTTPError("http://127.0.0.1", 500, "synthetic", Message(), None)

    _opener(monkeypatch, opened)
    with pytest.raises(
        (ValueError, UnicodeDecodeError), match=r"max_response_bytes|utf-8|collect local"
    ):
        controls._fetch_metadata("http://127.0.0.1", "version_before", MODEL, 2, 16)


def test_redirects_are_refused_without_following_a_location() -> None:
    with pytest.raises(ValueError, match="redirects are forbidden"):
        controls._NoRedirect().redirect_request(
            None, None, 302, "redirect", {}, "https://remote.invalid"
        )

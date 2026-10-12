"""Durable draft inventory and offline replay reject incomplete or changed evidence."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from notebook_to_kedro import plan_notebook_path
from notebook_to_kedro.evaluation import notebook_capture as capture_module
from notebook_to_kedro.evaluation.notebook_body import NotebookBodyRecord
from notebook_to_kedro.evaluation.notebook_capture import (
    NotebookBodyCapture,
    create_notebook_body_capture,
    load_notebook_body_capture,
    record_notebook_body_response,
    replay_notebook_body_capture,
    reserve_notebook_body_request,
)
from notebook_to_kedro.evaluation.notebook_sources import (
    NotebookSourceBinding,
    create_notebook_source_binding,
)
from notebook_to_kedro.exceptions import BehavioralBenchmarkArtifactError
from notebook_to_kedro.generation.code import NodeBodyResponse

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = Path("tests/fixtures/evaluation/pilots/customer_churn_v1/contract.json")
NOTEBOOK = Path("tests/fixtures/notebooks/pilots/customer_churn_v1/customer_churn.ipynb")


@pytest.fixture(scope="module")
def binding() -> NotebookSourceBinding:
    return _bind(ROOT)


def _bind(root: Path) -> NotebookSourceBinding:
    return create_notebook_source_binding(
        plan_notebook_path(root / NOTEBOOK, project_root=root),
        project_root=root,
        contract_path=CONTRACT,
        expected_catalog_path=CONTRACT.with_name("expected_catalog.yml"),
    )


def _create(path: Path, binding: NotebookSourceBinding, **kwargs: Any) -> Path:
    return create_notebook_body_capture(
        path,
        binding,
        project_root=ROOT,
        provider_name="offline-fixture",
        model_name="trusted-source-echo",
        prompt_version="fixture-1",
        **kwargs,
    )


def _reserve(path: Path, binding: NotebookSourceBinding, index: int = 0) -> str:
    identifier = binding.requests[index].request_id
    reserve_notebook_body_request(path, binding, identifier, project_root=ROOT)
    return identifier


def _record(path: Path, binding: NotebookSourceBinding, record: NotebookBodyRecord) -> None:
    record_notebook_body_response(path, binding, record, project_root=ROOT)


def _load(path: Path, binding: NotebookSourceBinding) -> NotebookBodyCapture:
    return load_notebook_body_capture(path, binding, project_root=ROOT)


def _rewrite(path: Path, key: str, value: Any) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[key] = value
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_empty_partial_and_complete_inventory_replay(
    tmp_path: Path,
    binding: NotebookSourceBinding,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("offline capture must not call a model or execute code")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("nbclient.NotebookClient.execute", forbidden)
    path = _create(tmp_path / "capture", binding)
    empty = _load(path, binding)
    assert empty.missing_request_ids == tuple(r.request_id for r in binding.requests)
    assert not empty.complete
    assert empty.attempted_request_ids == empty.unfinished_request_ids == ()
    assert empty.provider_name == "offline-fixture"
    assert empty.model_name == "trusted-source-echo"
    assert empty.prompt_version == "fixture-1"
    identifier = _reserve(path, binding)
    partial = _load(path, binding)
    assert partial.unfinished_request_ids == (identifier,)
    assert partial.content_sha256 != empty.content_sha256
    report = replay_notebook_body_capture(path, binding, project_root=ROOT)
    assert report.batch.planned_count == 9
    assert report.batch.accepted_count == 0
    assert report.batch.module_source is None
    assert all(p.status == "not_requested" for p in report.batch.proposals)
    # Complete the same explicit reservation, without re-reserving or provider calls.
    for index, request in enumerate(binding.requests):
        if index:
            _reserve(path, binding, index)
        source = request.raw_source
        if request.node_name == "join_customer_features":
            source = source.replace(
                '{"net_revenue": 0.0, "completed_orders": 0}',
                "join_customer_features_fillna_values",
            )
        raw = (
            "\n"
            + NodeBodyResponse("1.0", request.request_id, request.task_id, source).to_json()
            + "\n"
        )
        _record(path, binding, NotebookBodyRecord(request.request_id, raw))
    complete = _load(path, binding)
    assert complete.complete
    assert complete.missing_request_ids == complete.unfinished_request_ids == ()
    assert len(complete.records) == 9
    assert all(
        r.raw_response is not None and r.raw_response.startswith("\n") for r in complete.records
    )
    before = {p.relative_to(path): p.read_bytes() for p in path.rglob("*.json")}
    for _ in range(2):
        report = replay_notebook_body_capture(path, binding, project_root=ROOT)
        assert report.batch.static_ready
        assert report.batch.accepted_count == report.batch.planned_count == 9
        assert json.loads(report.binding.review_json)["status"] == "pending"
        assert _load(path, binding) == complete
    assert before == {p.relative_to(path): p.read_bytes() for p in path.rglob("*.json")}


@pytest.mark.parametrize("raw", ["", "not json", "\ud800", '"' * 300, "{}"])
def test_raw_invalid_evidence_is_saved_before_parsing(
    tmp_path: Path,
    binding: NotebookSourceBinding,
    raw: str,
) -> None:
    path = _create(tmp_path / "capture", binding, max_response_bytes=100)
    identifier = _reserve(path, binding)
    record = NotebookBodyRecord(identifier, raw)
    _record(path, binding, record)
    assert _load(path, binding).records == (record,)
    report = replay_notebook_body_capture(path, binding, project_root=ROOT)
    assert report.batch.proposals[0].status == "invalid_response"
    assert report.batch.proposals[0].record == record
    assert report.batch.module_source is None
    assert report.batch.planned_count == 9


def test_provider_error_and_out_of_order_records(
    tmp_path: Path, binding: NotebookSourceBinding
) -> None:
    path = _create(tmp_path / "capture", binding)
    second = _reserve(path, binding, 1)
    first = _reserve(path, binding, 0)
    _record(path, binding, NotebookBodyRecord(second, provider_error=("timeout", "offline error")))
    _record(path, binding, NotebookBodyRecord(first, "{}"))
    capture = _load(path, binding)
    assert capture.attempted_request_ids == (first, second)
    assert [r.request_id for r in capture.records] == [first, second]
    assert capture.unfinished_request_ids == ()
    report = replay_notebook_body_capture(path, binding, project_root=ROOT)
    assert report.batch.proposals[1].status == "provider_error"
    assert report.batch.proposals[1].diagnostic_code == "timeout"
    assert report.batch.module_source is None


def test_exclusive_capture_reservations_and_outcomes(
    tmp_path: Path, binding: NotebookSourceBinding
) -> None:
    path = _create(tmp_path / "capture", binding)
    with pytest.raises(FileExistsError):
        _create(path, binding)
    with pytest.raises(ValueError, match="unknown"):
        reserve_notebook_body_request(path, binding, "../unknown", project_root=ROOT)
    with pytest.raises(ValueError, match="reservation"):
        _record(path, binding, NotebookBodyRecord(binding.requests[0].request_id, "{}"))
    identifier = _reserve(path, binding)
    with pytest.raises(BehavioralBenchmarkArtifactError, match="already exists"):
        _reserve(path, binding)
    _record(path, binding, NotebookBodyRecord(identifier, "{}"))
    with pytest.raises(BehavioralBenchmarkArtifactError, match="already exists"):
        _record(path, binding, NotebookBodyRecord(identifier, "changed"))
    assert _load(path, binding).records == (NotebookBodyRecord(identifier, "{}"),)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
@pytest.mark.parametrize("name", ["max_response_bytes", "max_file_bytes"])
def test_invalid_limits_fail_before_creation(
    tmp_path: Path,
    binding: NotebookSourceBinding,
    limit: Any,
    name: str,
) -> None:
    with pytest.raises(ValueError, match="positive integers"):
        _create(tmp_path / "capture", binding, **{name: limit})
    assert not (tmp_path / "capture").exists()


def test_size_bounds_cover_manifest_read_and_response_publication(
    tmp_path: Path,
    binding: NotebookSourceBinding,
) -> None:
    with pytest.raises(ValueError, match="exceeds"):
        _create(tmp_path / "small", binding, max_file_bytes=10)
    assert not (tmp_path / "small").exists()
    path = _create(tmp_path / "capture", binding)
    with pytest.raises(ValueError, match="positive"):
        load_notebook_body_capture(path, binding, project_root=ROOT, max_file_bytes=0)
    size = (path / "manifest.json").stat().st_size
    assert load_notebook_body_capture(path, binding, project_root=ROOT, max_file_bytes=size)
    with pytest.raises(ValueError, match="exceeds"):
        load_notebook_body_capture(path, binding, project_root=ROOT, max_file_bytes=size - 1)
    identifier = _reserve(path, binding)
    with pytest.raises(ValueError, match="exceeds"):
        record_notebook_body_response(
            path,
            binding,
            NotebookBodyRecord(identifier, "x" * (size + 1)),
            project_root=ROOT,
            max_file_bytes=size,
        )
    assert _load(path, binding).unfinished_request_ids == (identifier,)
    assert not list((path / "responses").iterdir())


@pytest.mark.parametrize("stage", ["manifest", "reservation", "response"])
def test_publication_failure_never_fabricates_an_outcome(
    tmp_path: Path,
    binding: NotebookSourceBinding,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    path = tmp_path / "capture"
    if stage != "manifest":
        _create(path, binding)
    if stage == "response":
        _reserve(path, binding)

    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise BehavioralBenchmarkArtifactError("controlled publication failure")

    monkeypatch.setattr(capture_module, "write_json_exclusive", fail)

    def publish() -> None:
        if stage == "manifest":
            _create(path, binding)
        elif stage == "reservation":
            _reserve(path, binding)
        else:
            _record(path, binding, NotebookBodyRecord(binding.requests[0].request_id, "{}"))

    with pytest.raises(BehavioralBenchmarkArtifactError, match="publication failure"):
        publish()
    assert not list((path / "responses").iterdir())
    if stage == "manifest":
        with pytest.raises(ValueError, match="layout"):
            _load(path, binding)
    else:
        assert not _load(path, binding).complete


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("schema_version", "unknown"),
        ("validator_version", "unknown"),
        ("binding", {}),
        ("extra", 1),
        ("provider_name", ""),
        ("model_name", 7),
        ("prompt_version", " "),
        ("max_response_bytes", True),
        ("max_response_bytes", 0),
    ],
)
def test_manifest_schema_and_binding_rejected(
    tmp_path: Path,
    binding: NotebookSourceBinding,
    key: str,
    value: Any,
) -> None:
    path = _create(tmp_path / "capture", binding)
    _rewrite(path / "manifest.json", key, value)
    with pytest.raises(ValueError, match=r"capture|must"):
        _load(path, binding)


@pytest.mark.parametrize("payload", ['{"x":1,"x":2}', '{"x":NaN}', "[]", "broken"])
def test_malformed_manifest_json_rejected(
    tmp_path: Path,
    binding: NotebookSourceBinding,
    payload: str,
) -> None:
    path = _create(tmp_path / "capture", binding)
    (path / "manifest.json").write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match=r"Duplicate|duplicate|non-finite|must|Expecting"):
        _load(path, binding)


@pytest.mark.parametrize("folder", ["attempts", "responses"])
def test_unknown_inventory_entry_rejected(
    tmp_path: Path,
    binding: NotebookSourceBinding,
    folder: str,
) -> None:
    path = _create(tmp_path / "capture", binding)
    (path / folder / "unknown.txt").write_text("evidence", encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected capture inventory"):
        _load(path, binding)


@pytest.mark.parametrize("folder", ["attempts", "responses"])
def test_missing_inventory_directory_rejected(
    tmp_path: Path,
    binding: NotebookSourceBinding,
    folder: str,
) -> None:
    path = _create(tmp_path / "capture", binding)
    (path / folder).rmdir()
    (path / folder).write_text("not a directory", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory requires"):
        _load(path, binding)


def test_non_regular_manifest_and_extra_root_entry_rejected(
    tmp_path: Path,
    binding: NotebookSourceBinding,
) -> None:
    path = _create(tmp_path / "capture", binding)
    (path / "extra").mkdir()
    with pytest.raises(ValueError, match="layout"):
        _load(path, binding)
    (path / "extra").rmdir()
    (path / "manifest.json").unlink()
    (path / "manifest.json").mkdir()
    with pytest.raises(ValueError, match="regular"):
        _load(path, binding)


@pytest.mark.parametrize(
    ("key", "value"), [("request_id", "wrong"), ("manifest_sha256", "0" * 64), ("extra", 1)]
)
def test_corrupt_reservation_rejected(
    tmp_path: Path,
    binding: NotebookSourceBinding,
    key: str,
    value: Any,
) -> None:
    path = _create(tmp_path / "capture", binding)
    _reserve(path, binding)
    _rewrite(next((path / "attempts").iterdir()), key, value)
    with pytest.raises(ValueError, match="capture"):
        _load(path, binding)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("request_id", "wrong"),
        ("manifest_sha256", "0" * 64),
        ("extra", 1),
        ("raw_response", "changed"),
        ("raw_response_sha256", "0" * 64),
        ("raw_response", 7),
        ("provider_error", "bad"),
        ("provider_error", []),
        ("provider_error", ["", "message"]),
        ("provider_error", ["code", "message"]),
    ],
)
def test_corrupt_response_rejected(
    tmp_path: Path,
    binding: NotebookSourceBinding,
    key: str,
    value: Any,
) -> None:
    path = _create(tmp_path / "capture", binding)
    identifier = _reserve(path, binding)
    _record(path, binding, NotebookBodyRecord(identifier, "{}"))
    _rewrite(next((path / "responses").iterdir()), key, value)
    with pytest.raises(ValueError, match=r"capture|must|exactly one"):
        _load(path, binding)


def test_response_without_reservation_and_metadata_drift_rejected(
    tmp_path: Path,
    binding: NotebookSourceBinding,
) -> None:
    path = _create(tmp_path / "capture", binding)
    identifier = _reserve(path, binding)
    _record(path, binding, NotebookBodyRecord(identifier, "{}"))
    reservation = next((path / "attempts").iterdir())
    data = reservation.read_bytes()
    reservation.unlink()
    with pytest.raises(ValueError, match="reservation"):
        _load(path, binding)
    reservation.write_bytes(data)
    _rewrite(path / "manifest.json", "model_name", "changed-model")
    with pytest.raises(ValueError, match="attempt identity"):
        _load(path, binding)


def test_changed_sources_rejected_before_replay_or_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "project"
    for relative in (CONTRACT.parent, NOTEBOOK.parent):
        shutil.copytree(ROOT / relative, root / relative)
    binding = _bind(root)
    path = create_notebook_body_capture(
        tmp_path / "capture",
        binding,
        project_root=root,
        provider_name="offline",
        model_name="fixed",
        prompt_version="fixture",
    )
    source = root / CONTRACT
    source.write_bytes(source.read_bytes() + b"\n")

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("stale evidence must stop before parsing proposals or writing")

    monkeypatch.setattr(capture_module, "validate_source_bound_notebook_body_batch", forbidden)
    monkeypatch.setattr(capture_module, "write_json_exclusive", forbidden)
    for action in (
        lambda: replay_notebook_body_capture(path, binding, project_root=root),
        lambda: reserve_notebook_body_request(
            path, binding, binding.requests[0].request_id, project_root=root
        ),
        lambda: record_notebook_body_response(
            path,
            binding,
            NotebookBodyRecord(binding.requests[0].request_id, "{}"),
            project_root=root,
        ),
    ):
        with pytest.raises(ValueError, match="changed"):
            action()
    assert not list((path / "attempts").iterdir())


def test_new_request_prefix_cannot_reuse_existing_capture(
    tmp_path: Path,
    binding: NotebookSourceBinding,
) -> None:
    path = _create(tmp_path / "capture", binding)
    new = create_notebook_source_binding(
        binding.plan,
        project_root=ROOT,
        contract_path=CONTRACT,
        expected_catalog_path=CONTRACT.with_name("expected_catalog.yml"),
        request_prefix="new",
    )
    with pytest.raises(ValueError, match="exact draft binding"):
        _load(path, new)
    with pytest.raises(ValueError, match="hash mismatch"):
        _load(path, replace(binding, content_sha256="0" * 64))


def test_redirected_file_and_linked_inventory_rejected(
    tmp_path: Path,
    binding: NotebookSourceBinding,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _create(tmp_path / "capture", binding)
    resolve = Path.resolve

    def redirected(self: Path, *args: Any, **kwargs: Any) -> Path:
        if self == path / "manifest.json":
            return tmp_path / "outside.json"
        return resolve(self, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Path, "resolve", redirected)
        with pytest.raises(ValueError, match="contained"):
            _load(path, binding)
    is_symlink = Path.is_symlink

    def linked(self: Path) -> bool:
        return self == path / "attempts" or is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", linked)
    with pytest.raises(ValueError, match="inventory requires"):
        _load(path, binding)


def test_known_inventory_name_cannot_be_a_directory(
    tmp_path: Path,
    binding: NotebookSourceBinding,
) -> None:
    path = _create(tmp_path / "capture", binding)
    (path / "attempts" / capture_module._filename(binding.requests[0].request_id)).mkdir()
    with pytest.raises(ValueError, match="regular"):
        _load(path, binding)


def test_complete_error_inventory_is_not_static_success(
    tmp_path: Path,
    binding: NotebookSourceBinding,
) -> None:
    path = _create(tmp_path / "capture", binding)
    for index, request in enumerate(binding.requests):
        _reserve(path, binding, index)
        _record(
            path,
            binding,
            NotebookBodyRecord(request.request_id, provider_error=("error", "failed")),
        )
    assert _load(path, binding).complete
    report = replay_notebook_body_capture(path, binding, project_root=ROOT)
    assert report.batch.planned_count == 9
    assert report.batch.accepted_count == 0
    assert report.batch.module_source is None


def test_numerically_equal_binding_json_is_not_exact_evidence(
    tmp_path: Path,
    binding: NotebookSourceBinding,
) -> None:
    path = _create(tmp_path / "capture", binding)
    manifest_path = path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    size = manifest["binding"]["files"][0]["size_bytes"]
    manifest["binding"]["files"][0]["size_bytes"] = float(size)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="exact draft binding"):
        _load(path, binding)

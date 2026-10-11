"""Draft source identity checks reject drift before recorded proposal validation."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

import pytest
from nbclient import NotebookClient

from notebook_to_kedro import plan_notebook_path
from notebook_to_kedro.analysis import analyze_notebook
from notebook_to_kedro.evaluation import (
    NotebookSourceBinding,
    create_notebook_source_binding,
    validate_source_bound_notebook_body_batch,
    verify_notebook_source_binding,
)
from notebook_to_kedro.evaluation import notebook_sources as source_module
from notebook_to_kedro.ir import CatalogDataset, ConversionPlan, NotebookFacts
from notebook_to_kedro.notebook import LoadedNotebook, load_notebook

ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = Path("tests/fixtures/evaluation/pilots/customer_churn_v1/contract.json")
CATALOG_PATH = CONTRACT_PATH.with_name("expected_catalog.yml")
NOTEBOOK_PATH = Path("tests/fixtures/notebooks/pilots/customer_churn_v1/customer_churn.ipynb")


@dataclass
class _Pilot:
    root: Path
    plan: ConversionPlan

    def contract(self) -> dict[str, Any]:
        return cast(
            "dict[str, Any]", json.loads((self.root / CONTRACT_PATH).read_text(encoding="utf-8"))
        )

    def write_contract(self, data: dict[str, Any]) -> None:
        (self.root / CONTRACT_PATH).write_text(json.dumps(data), encoding="utf-8")

    def bind(self, **kwargs: Any) -> NotebookSourceBinding:
        return create_notebook_source_binding(
            self.plan,
            project_root=self.root,
            contract_path=CONTRACT_PATH,
            expected_catalog_path=CATALOG_PATH,
            **kwargs,
        )


@pytest.fixture
def pilot(tmp_path: Path) -> _Pilot:
    for relative in (CONTRACT_PATH.parent, NOTEBOOK_PATH.parent):
        shutil.copytree(ROOT / relative, tmp_path / relative)
    return _Pilot(tmp_path, plan_notebook_path(tmp_path / NOTEBOOK_PATH, project_root=tmp_path))


def _rehash(binding: NotebookSourceBinding) -> NotebookSourceBinding:
    return replace(binding, content_sha256=source_module._binding_sha256(binding))


def test_binding_retains_four_file_identities_requests_and_pending_review(pilot: _Pilot) -> None:
    binding = pilot.bind(request_prefix="attempt-1")
    assert binding.case_id == "synthetic-customer-churn-v1"
    assert len(binding.content_sha256) == 64
    assert binding.plan == pilot.plan
    assert len(binding.requests) == 9
    assert binding.requests[0].request_id == "attempt-1:task-0003"
    assert [identity.role for identity in binding.files] == [
        "contract",
        "notebook",
        "expected_catalog",
        "dataset:orders",
    ]
    for identity in binding.files:
        data = (pilot.root / identity.path).read_bytes()
        assert identity.sha256 == hashlib.sha256(data).hexdigest()
        assert identity.size_bytes == len(data)
        assert not Path(identity.path).is_absolute()
    assert json.loads(binding.review_json) == pilot.contract()["review"]
    assert json.loads(binding.review_json)["status"] == "pending"
    assert pilot.bind(request_prefix="attempt-1") == binding
    verify_notebook_source_binding(binding, project_root=pilot.root)


def test_bound_batch_reads_only_and_retains_full_missing_denominator(
    pilot: _Pilot, monkeypatch: pytest.MonkeyPatch
) -> None:
    binding = pilot.bind()

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("binding must not contact a provider, execute cells or write files")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    report = validate_source_bound_notebook_body_batch(binding, (), project_root=pilot.root)
    assert report.binding is binding
    assert report.batch.planned_count == 9
    assert report.batch.accepted_count == 0
    assert not report.batch.static_ready
    assert report.batch.module_source is None


@pytest.mark.parametrize("role", ["contract", "notebook", "expected_catalog", "dataset:orders"])
def test_any_byte_drift_stops_before_batch_validation(
    pilot: _Pilot, monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    binding = pilot.bind()
    identity = next(identity for identity in binding.files if identity.role == role)
    path = pilot.root / identity.path
    path.write_bytes(path.read_bytes() + b"\n")

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("drift must be rejected before processing recorded responses")

    monkeypatch.setattr(source_module, "validate_notebook_body_batch", forbidden)
    with pytest.raises(ValueError, match=r"hash does not match|binding changed"):
        validate_source_bound_notebook_body_batch(binding, (), project_root=pilot.root)


@pytest.mark.parametrize("role", ["contract", "notebook", "expected_catalog", "dataset:orders"])
def test_missing_file_is_rejected(pilot: _Pilot, role: str) -> None:
    binding = pilot.bind()
    identity = next(identity for identity in binding.files if identity.role == role)
    (pilot.root / identity.path).unlink()
    with pytest.raises(ValueError, match="Cannot read bound file"):
        verify_notebook_source_binding(binding, project_root=pilot.root)


@pytest.mark.parametrize("limit", [True, 0, -1, 1.5])
def test_bad_file_limits_fail(pilot: _Pilot, limit: Any) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        pilot.bind(max_file_bytes=limit)


def test_file_read_is_bounded(pilot: _Pilot) -> None:
    with pytest.raises(ValueError, match="exceeds max_file_bytes"):
        pilot.bind(max_file_bytes=1)


def test_catalog_reference_must_be_a_regular_file(pilot: _Pilot) -> None:
    with pytest.raises(ValueError, match="not a regular file"):
        create_notebook_source_binding(
            pilot.plan,
            project_root=pilot.root,
            contract_path=CONTRACT_PATH,
            expected_catalog_path=CATALOG_PATH.parent,
        )


def test_file_open_failure_is_reported(pilot: _Pilot, monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: Any, **_kwargs: Any) -> None:
        raise PermissionError("controlled read failure")

    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(ValueError, match="Cannot read bound file: contract"):
        pilot.bind()


def test_limit_is_inclusive_and_part_of_binding(pilot: _Pilot) -> None:
    largest = max(identity.size_bytes for identity in pilot.bind().files)
    binding = pilot.bind(max_file_bytes=largest)
    verify_notebook_source_binding(binding, project_root=pilot.root)
    assert binding.content_sha256 != pilot.bind(max_file_bytes=largest + 1).content_sha256


def test_invalid_root(pilot: _Pilot) -> None:
    with pytest.raises(ValueError, match="existing directory"):
        create_notebook_source_binding(
            pilot.plan,
            project_root=pilot.root / "missing",
            contract_path=CONTRACT_PATH,
            expected_catalog_path=CATALOG_PATH,
        )


@pytest.mark.parametrize("field", ["contract", "catalog", "notebook", "dataset"])
def test_paths_cannot_escape_root(pilot: _Pilot, field: str) -> None:
    kwargs: dict[str, Any] = {}
    if field in {"contract", "catalog"}:
        kwargs["contract_path" if field == "contract" else "expected_catalog_path"] = (
            pilot.root.parent / "outside"
        )
    else:
        data = pilot.contract()
        descriptor = data["notebook"] if field == "notebook" else data["sources"][1]
        descriptor["path"] = "../outside"
        pilot.write_contract(data)
    with pytest.raises(ValueError, match="escapes project_root"):
        create_notebook_source_binding(
            pilot.plan,
            project_root=pilot.root,
            contract_path=kwargs.get("contract_path", CONTRACT_PATH),
            expected_catalog_path=kwargs.get("expected_catalog_path", CATALOG_PATH),
        )


def test_absolute_contract_source_path_is_rejected(pilot: _Pilot) -> None:
    data = pilot.contract()
    data["notebook"]["path"] = str(pilot.root / NOTEBOOK_PATH)
    pilot.write_contract(data)
    with pytest.raises(ValueError, match="project-relative"):
        pilot.bind()


@pytest.mark.parametrize(
    "payload", ["{", "[]", '{"schema_version":"a","schema_version":"b"}', '{"extra":NaN}']
)
def test_invalid_contract_json(pilot: _Pilot, payload: str) -> None:
    (pilot.root / CONTRACT_PATH).write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError, match=r"Expecting|object|duplicate|non-finite"):
        pilot.bind()


@pytest.mark.parametrize(
    ("section", "field", "value", "message"),
    [
        (None, "schema_version", "approved-v1", "pilot-draft-1"),
        (None, "case_id", " ", "must not be empty"),
        (None, "case_id", 1, "must be a string"),
        (None, "notebook", [], "must be an object"),
        (None, "review", [], "must be an object"),
        (None, "sources", {}, "non-empty array"),
        (None, "sources", [], "non-empty array"),
        ("notebook", "sha256", "bad", "invalid declared SHA"),
        ("notebook", "sha256", 1, "must be a string"),
        ("notebook", "sha256", "0" * 64, "hash does not match"),
        ("notebook", "path", "", "must not be empty"),
        ("review", "status", "approved", "pending human review"),
        ("review", "independent_human_review", True, "pending human review"),
        ("review", "independent_human_review", 0, "pending human review"),
        ("review", "reviewed_by", "human", "pending human review"),
        ("review", "provenance", "", "must not be empty"),
        ("review", "local_benchmark_provider_exposure", None, "must be a string"),
    ],
)
def test_invalid_contract_metadata(
    pilot: _Pilot, section: str | None, field: str, value: Any, message: str
) -> None:
    data = pilot.contract()
    target = data if section is None else data[section]
    target[field] = value
    pilot.write_contract(data)
    with pytest.raises(ValueError, match=message):
        pilot.bind()


def test_missing_reviewer_field_cannot_imply_pending_review(pilot: _Pilot) -> None:
    data = pilot.contract()
    del data["review"]["reviewed_by"]
    pilot.write_contract(data)
    with pytest.raises(ValueError, match="pending human review"):
        pilot.bind()


@pytest.mark.parametrize("kind", ["wrong_type", "duplicate", "unsupported", "missing_catalog"])
def test_bad_source_inventory(pilot: _Pilot, kind: str) -> None:
    data = pilot.contract()
    if kind == "wrong_type":
        data["sources"][0] = None
    elif kind == "duplicate":
        data["sources"].append(data["sources"][0])
    elif kind == "unsupported":
        data["sources"][0]["kind"] = "spark"
    else:
        data["sources"] = data["sources"][:1]
    pilot.write_contract(data)
    with pytest.raises(ValueError, match=r"object|duplicate|only simulation|every catalog"):
        pilot.bind()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("catalog_entry", True),
        ("name", "absent"),
        ("name", "orders"),
        ("path", "invented.csv"),
        ("sha256", "0" * 64),
    ],
)
def test_simulation_must_not_invent_catalog_files(pilot: _Pilot, field: str, value: Any) -> None:
    data = pilot.contract()
    data["sources"][0][field] = value
    pilot.write_contract(data)
    with pytest.raises(ValueError, match="simulation source"):
        pilot.bind()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("catalog_entry", False),
        ("catalog_entry", 1),
        ("catalog_type", "wrong"),
        ("generated_filepath", "wrong"),
        ("name", "absent"),
    ],
)
def test_catalog_declarations_must_match_plan(pilot: _Pilot, field: str, value: Any) -> None:
    data = pilot.contract()
    data["sources"][1][field] = value
    pilot.write_contract(data)
    with pytest.raises(ValueError, match="catalog source does not match"):
        pilot.bind()


@pytest.mark.parametrize("path", [None, "different.csv"])
def test_plan_catalog_file_must_be_exact_declared_file(pilot: _Pilot, path: str | None) -> None:
    dataset = replace(pilot.plan.catalog_datasets[0], source_filepath=path)
    pilot.plan = replace(pilot.plan, catalog_datasets=(dataset,))
    with pytest.raises(ValueError, match="catalog source does not match"):
        pilot.bind()


def test_every_plan_catalog_dataset_needs_a_source(pilot: _Pilot) -> None:
    extra = CatalogDataset("extra", "example", "extra.csv", "extra.csv")
    pilot.plan = replace(pilot.plan, catalog_datasets=(*pilot.plan.catalog_datasets, extra))
    with pytest.raises(ValueError, match="every catalog dataset"):
        pilot.bind()


def test_supplied_plan_path_cannot_point_to_another_notebook(pilot: _Pilot) -> None:
    pilot.plan = replace(pilot.plan, notebook_path="different.ipynb")
    with pytest.raises(ValueError, match="plan notebook path"):
        pilot.bind()


@pytest.mark.parametrize("change", ["source", "name", "imports"])
def test_plan_must_equal_rebuilt_deterministic_plan(pilot: _Pilot, change: str) -> None:
    task = pilot.plan.task_candidates[0]
    if change == "source":
        task = replace(task, source=task.source.replace("default_rng(7)", "default_rng(8)"))
    elif change == "name":
        task = replace(task, name="different_simulation")
    if change == "imports":
        pilot.plan = replace(pilot.plan, imports=(*pilot.plan.imports, "import math"))
    else:
        pilot.plan = replace(pilot.plan, task_candidates=(task, *pilot.plan.task_candidates[1:]))
    with pytest.raises(ValueError, match="deterministic notebook reconstruction"):
        pilot.bind()


def test_loader_hash_must_match_snapshot(pilot: _Pilot, monkeypatch: pytest.MonkeyPatch) -> None:
    loaded = load_notebook(pilot.root / NOTEBOOK_PATH, project_root=pilot.root)
    monkeypatch.setattr(
        source_module,
        "load_notebook",
        lambda *_args, **_kwargs: replace(loaded, content_sha256="0" * 64),
    )
    with pytest.raises(ValueError, match="notebook changed during"):
        pilot.bind()


def test_files_are_rechecked_after_static_reconstruction(
    pilot: _Pilot, monkeypatch: pytest.MonkeyPatch
) -> None:
    def changed(loaded: LoadedNotebook) -> NotebookFacts:
        result = analyze_notebook(loaded)
        path = pilot.root / NOTEBOOK_PATH.with_name("orders.csv")
        path.write_bytes(path.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(source_module, "analyze_notebook", changed)
    with pytest.raises(ValueError, match="changed during source binding: dataset:orders"):
        pilot.bind()


def test_new_contract_revision_requires_explicit_new_binding(pilot: _Pilot) -> None:
    binding = pilot.bind()
    data = pilot.contract()
    data["review"]["provenance"] += " Additional draft note."
    pilot.write_contract(data)
    with pytest.raises(ValueError, match="binding changed"):
        verify_notebook_source_binding(binding, project_root=pilot.root)
    new = pilot.bind()
    assert new.content_sha256 != binding.content_sha256
    assert json.loads(new.review_json)["status"] == "pending"
    verify_notebook_source_binding(new, project_root=pilot.root)


def test_unsupported_or_corrupt_binding_is_rejected(pilot: _Pilot) -> None:
    binding = pilot.bind()
    with pytest.raises(ValueError, match="unsupported"):
        verify_notebook_source_binding(
            replace(binding, schema_version="other"), project_root=pilot.root
        )
    with pytest.raises(ValueError, match="content hash mismatch"):
        verify_notebook_source_binding(
            replace(binding, content_sha256="0" * 64), project_root=pilot.root
        )


@pytest.mark.parametrize("role", ["contract", "expected_catalog"])
@pytest.mark.parametrize("duplicate", [False, True])
def test_required_roles_are_not_inferred_from_invalid_bindings(
    pilot: _Pilot, role: str, *, duplicate: bool
) -> None:
    binding = pilot.bind()
    files = tuple(identity for identity in binding.files if identity.role != role)
    if duplicate:
        identity = next(identity for identity in binding.files if identity.role == role)
        files = (*files, identity, identity)
    invalid = _rehash(replace(binding, files=files))
    with pytest.raises(ValueError, match=f"exactly one {role}"):
        verify_notebook_source_binding(invalid, project_root=pilot.root)


@pytest.mark.parametrize("field", ["requests", "case_id", "review_json", "files"])
def test_rehashing_cached_metadata_does_not_replace_reconstruction(
    pilot: _Pilot, field: str
) -> None:
    binding = pilot.bind()
    choices: dict[str, dict[str, Any]] = {
        "requests": {"requests": binding.requests[:-1]},
        "case_id": {"case_id": "invented"},
        "review_json": {"review_json": "{}"},
        "files": {"files": (replace(binding.files[0], size_bytes=1), *binding.files[1:])},
    }
    invalid = _rehash(replace(binding, **choices[field]))
    with pytest.raises(ValueError, match="binding changed"):
        verify_notebook_source_binding(invalid, project_root=pilot.root)


def test_binding_preserves_dataset_bytes_without_pandas_loading(
    pilot: _Pilot, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("source binding must not execute notebook cells")

    monkeypatch.setattr(NotebookClient, "execute", forbidden)
    binding = pilot.bind()
    assert len(binding.files) == 4

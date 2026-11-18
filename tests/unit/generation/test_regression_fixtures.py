"""Pinned fixture snapshots preserve explicit oracles and contained bounded reads."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from notebook_to_kedro import (
    GenerateRequest,
    PlanningResult,
    PlanRequest,
    WorkflowRegressionContract,
    load_local_project_configuration,
    load_workflow_regression_contract,
    run_local_operation,
)
from notebook_to_kedro.exceptions import LocalOperationError, WorkflowRegressionError
from notebook_to_kedro.generation.kedro import regression_contract as module


def _scenario(identifier: str = "positive") -> dict[str, Any]:
    return {
        "id": identifier,
        "inputs": {"values": -3.0},
        "parameters": {"scale": 2.0},
        "expected": 6.0,
    }


def _reference(content: bytes, path: str = "fixtures/one.json") -> dict[str, str]:
    return {"path": path, "sha256": hashlib.sha256(content).hexdigest()}


def _manifest(*references: dict[str, str]) -> dict[str, Any]:
    return {"schema_version": "1.1", "scenarios": list(references)}


def _write(tmp_path: Path, contents: tuple[bytes, ...]) -> Path:
    (tmp_path / "fixtures").mkdir(exist_ok=True)
    references = []
    for index, content in enumerate(contents):
        relative = f"fixtures/scenario_{index}.json"
        (tmp_path / relative).write_bytes(content)
        references.append(_reference(content, relative))
    path = tmp_path / "regression.json"
    path.write_text(json.dumps(_manifest(*references)), encoding="utf-8")
    return path


def test_committed_example_matches_the_existing_inline_expectations() -> None:
    root = Path(__file__).parents[3] / "examples/functional_workflow"
    inline = load_workflow_regression_contract(root / "regression.json")
    fixtures = load_workflow_regression_contract(root / "regression-fixtures.json")
    assert fixtures.resolved_dict() == inline.to_dict()
    assert len(fixtures.fixture_jsons) == 3


def test_large_fixture_is_an_immutable_identity_bound_snapshot(tmp_path: Path) -> None:
    data = _scenario()
    data["expected"] = "x" * (module.MAX_REGRESSION_BYTES + 1)
    content = json.dumps(data, indent=2).replace("\n", "\r\n").encode()
    path = _write(tmp_path, (content,))
    contract = load_workflow_regression_contract(path)
    assert contract.to_dict()["schema_version"] == "1.1"
    assert contract.fixture_jsons == (content.decode(),)
    assert contract.resolved_dict() == {"schema_version": "1.0", "scenarios": [data]}
    contract.resolved_dict()["scenarios"][0]["expected"] = "changed export"
    old_hash = contract.sha256
    (tmp_path / "fixtures/scenario_0.json").write_text("{}", encoding="utf-8")
    assert contract.resolved_dict()["scenarios"][0]["expected"] == data["expected"]
    assert contract.sha256 == old_hash
    with pytest.raises(WorkflowRegressionError, match="SHA-256"):
        load_workflow_regression_contract(path)
    assert (
        WorkflowRegressionContract.from_dict(
            contract.to_dict(), fixture_jsons=contract.fixture_jsons
        )
        == contract
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"extra": True},
        {"scenarios": None},
        {"scenarios": []},
        {"scenarios": [{}] * 101},
    ],
)
def test_manifest_structure_is_bounded(changes: dict[str, Any]) -> None:
    data = {**_manifest(_reference(b"{}")), **changes}
    with pytest.raises(WorkflowRegressionError):
        WorkflowRegressionContract.from_dict(data, fixture_jsons=("{}",))


@pytest.mark.parametrize(
    "reference",
    [
        None,
        {},
        {"path": "one.json"},
        {"path": 1, "sha256": "a" * 64},
        {"path": "../one.json", "sha256": "a" * 64},
        {"path": "/one.json", "sha256": "a" * 64},
        {"path": "C:/one.json", "sha256": "a" * 64},
        {"path": "fixtures\\one.json", "sha256": "a" * 64},
        {"path": "one.txt", "sha256": "a" * 64},
        {"path": "one.json", "sha256": None},
        {"path": "one.json", "sha256": "A" * 64},
        {"path": "CON.json", "sha256": "a" * 64},
    ],
)
def test_bad_references_are_rejected_before_file_reads(reference: Any) -> None:
    with pytest.raises(WorkflowRegressionError):
        WorkflowRegressionContract.from_dict(_manifest(reference), fixture_jsons=("{}",))


def test_case_aliases_and_missing_or_extra_captures_are_rejected() -> None:
    ref = _reference(b"{}")
    with pytest.raises(WorkflowRegressionError, match="distinct"):
        WorkflowRegressionContract.from_dict(_manifest(ref, {**ref, "path": "FIXTURES/ONE.json"}))
    for captures in ((), ("{}", "{}")):
        with pytest.raises(WorkflowRegressionError, match="every captured"):
            WorkflowRegressionContract.from_dict(_manifest(ref), fixture_jsons=captures)
    with pytest.raises(WorkflowRegressionError, match="immutable tuple"):
        WorkflowRegressionContract.from_dict(_manifest(ref), fixture_jsons=[])  # type: ignore[arg-type]
    with pytest.raises(WorkflowRegressionError, match="immutable UTF-8"):
        WorkflowRegressionContract.from_dict(_manifest(ref), fixture_jsons=(1,))  # type: ignore[arg-type]
    with pytest.raises(WorkflowRegressionError, match="Inline contracts"):
        WorkflowRegressionContract.from_dict(
            {"schema_version": "1.0", "scenarios": [_scenario()]}, fixture_jsons=("{}",)
        )


@pytest.mark.parametrize(
    "content",
    [
        b"{",
        b"[" * 2000,
        b"\xff",
        b'{"id":"one", "id":"two"}',
        b'{"id":"one","inputs":{},"parameters":{},"expected":NaN}',
        b'{"id":"one","inputs":{},"parameters":{},"expected":Infinity}',
        b'{"id":"one","inputs":{},"parameters":{},"expected":1,"extra":0}',
    ],
)
def test_malformed_or_nonfinite_fixtures_never_become_oracles(
    tmp_path: Path, content: bytes
) -> None:
    with pytest.raises(WorkflowRegressionError):
        load_workflow_regression_contract(_write(tmp_path, (content,)))


def test_duplicate_scenario_ids_and_deep_payloads_stay_invalid(tmp_path: Path) -> None:
    content = json.dumps(_scenario()).encode()
    with pytest.raises(WorkflowRegressionError, match="unique"):
        load_workflow_regression_contract(_write(tmp_path, (content, content)))
    nested: Any = 0
    for _ in range(17):
        nested = [nested]
    data = {**_scenario(), "expected": nested}
    with pytest.raises(WorkflowRegressionError, match="nesting"):
        load_workflow_regression_contract(_write(tmp_path, (json.dumps(data).encode(),)))


def test_file_and_aggregate_limits_apply_to_loader_and_direct_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = json.dumps(_scenario()).encode()
    path = _write(tmp_path, (content,))
    monkeypatch.setattr(module, "MAX_REGRESSION_FIXTURE_BYTES", len(content) - 1)
    with pytest.raises(WorkflowRegressionError, match="budget"):
        load_workflow_regression_contract(path)
    with pytest.raises(WorkflowRegressionError, match="budget"):
        WorkflowRegressionContract.from_dict(
            _manifest(_reference(content)), fixture_jsons=(content.decode(),)
        )
    monkeypatch.setattr(module, "MAX_REGRESSION_FIXTURE_BYTES", len(content))
    other = json.dumps(_scenario("other")).encode()
    path = _write(tmp_path, (content, other))
    monkeypatch.setattr(module, "MAX_REGRESSION_FIXTURE_TOTAL_BYTES", len(content) + len(other) - 1)
    with pytest.raises(WorkflowRegressionError, match="budget"):
        load_workflow_regression_contract(path)
    data = _manifest(_reference(content), _reference(other, "fixtures/other.json"))
    with pytest.raises(WorkflowRegressionError, match="budget"):
        WorkflowRegressionContract.from_dict(data, fixture_jsons=(content.decode(), other.decode()))
    monkeypatch.setattr(module, "MAX_REGRESSION_FIXTURE_TOTAL_BYTES", len(content) + len(other))
    assert len(load_workflow_regression_contract(path).fixture_jsons) == 2


@pytest.mark.parametrize("kind", ["missing", "directory", "link", "reparse", "special", "escape"])
def test_only_contained_regular_fixture_files_can_be_captured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    path = _write(tmp_path, (json.dumps(_scenario()).encode(),))
    fixture = tmp_path / "fixtures/scenario_0.json"
    if kind == "missing":
        fixture.unlink()
    elif kind == "directory":
        fixture.unlink()
        fixture.mkdir()
    elif kind == "escape":
        original_resolve = Path.resolve
        monkeypatch.setattr(
            Path,
            "resolve",
            lambda self: (
                tmp_path.parent / "outside.json" if self == fixture else original_resolve(self)
            ),
        )
    else:
        original_lstat = Path.lstat

        def lstat(self: Path) -> Any:
            if self == fixture:
                mode = (
                    stat.S_IFLNK
                    if kind == "link"
                    else stat.S_IFIFO
                    if kind == "special"
                    else stat.S_IFREG
                )
                return SimpleNamespace(
                    st_mode=mode, st_file_attributes=0x400 if kind == "reparse" else 0
                )
            return original_lstat(self)

        monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(WorkflowRegressionError):
        load_workflow_regression_contract(path)


def test_local_operations_reload_fixtures_and_refuse_drift_before_publication(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.py"
    source.write_text(
        "def identity(values):\n    return values\n\ndef workflow(values):\n"
        "    total = identity(values)\n    return total\n",
        encoding="utf-8",
    )
    scenario = {"id": "one", "inputs": {"values": 1.0}, "parameters": {}, "expected": 1.0}
    contract = _write(tmp_path, (json.dumps(scenario).encode(),))
    (tmp_path / "workflow.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "entrypoint": "workflow",
                "inputs": {"values": "values.json"},
                "parameters": {},
                "outputs": {"total": "data/08_reporting/total.json"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "values.json").write_text("1.0", encoding="utf-8")
    settings = tmp_path / "project.json"
    settings.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project_root": ".",
                "source_kind": "functional",
                "source": "source.py",
                "workflow_configuration": "workflow.json",
                "regression_contract": contract.name,
            }
        ),
        encoding="utf-8",
    )
    config = load_local_project_configuration(settings)
    preview = run_local_operation(PlanRequest(config))
    assert isinstance(preview, PlanningResult)
    assert any(f.path.startswith("tests/regression_fixtures/") for f in preview.files)
    (tmp_path / "fixtures/scenario_0.json").write_text("{}", encoding="utf-8")
    target = tmp_path / "output"
    with pytest.raises(LocalOperationError, match="SHA-256"):
        run_local_operation(GenerateRequest(config, target))
    assert not target.exists()

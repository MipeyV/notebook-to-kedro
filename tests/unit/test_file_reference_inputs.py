"""Raw file-reference contracts preserve bytes and reject unsupported boundary assumptions."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from notebook_to_kedro import (
    FileReferenceInput,
    FunctionalWorkflowConfiguration,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    load_workflow_regression_contract,
    plan_functional_workflow_path,
)
from notebook_to_kedro.analysis import file_inputs as capture
from notebook_to_kedro.exceptions import (
    FunctionalWorkflowError,
    ProjectGenerationError,
    WorkflowRegressionError,
)
from notebook_to_kedro.generation.kedro.functional import render_functional_workflow
from notebook_to_kedro.semantic.functional_workflow import plan_functional_workflow

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_files"
SOURCE = EXAMPLE / "src/reference_ml/workflow.py"


def _configuration() -> FunctionalWorkflowConfiguration:
    return load_functional_workflow_configuration(EXAMPLE / "workflow.json")


@pytest.fixture
def workspace(tmp_path: Path) -> tuple[Path, FunctionalWorkflowConfiguration]:
    shutil.copytree(EXAMPLE, tmp_path / "example")
    data: Any = _configuration().to_dict()
    data["source_package"] = "example/src/reference_ml"
    for value in data["file_inputs"].values():
        value["path"] = value["path"].replace("examples/functional_files", "example")
        value["sidecars"] = [
            path.replace("examples/functional_files", "example") for path in value["sidecars"]
        ]
    return (
        tmp_path / "example/src/reference_ml/workflow.py",
        FunctionalWorkflowConfiguration.from_dict(data),
    )


def test_reference_configuration_is_explicit_immutable_and_exports_fresh_values() -> None:
    config = _configuration()
    data: Any = config.to_dict()
    assert FunctionalWorkflowConfiguration.from_dict(data) == config
    data["file_inputs"]["snapshot_path"]["sidecars"].append("changed")
    assert config == _configuration()
    for version in ("1.0", "1.1", "1.2", "1.3"):
        with pytest.raises(FunctionalWorkflowError, match=r"schema 1\.4"):
            replace(
                config,
                schema_version=version,
                source_package=config.source_package if version == "1.3" else None,
            )


@pytest.mark.parametrize(
    "path", [None, "", ".", "/outside", "../outside", "x/../y", "x/./y", "x\\y", "C:outside"]
)
def test_reference_paths_are_normalized_contained_posix(path: Any) -> None:
    with pytest.raises(FunctionalWorkflowError):
        FileReferenceInput(path)


@pytest.mark.parametrize(
    "sidecars",
    [
        ["a.json"],
        (None,),
        ("../b",),
        ("a.txt",),
        ("a.json", "a.json"),
        ("other/a.json",),
        tuple(f"meta_{i}" for i in range(17)),
    ],
)
def test_sidecars_must_be_bounded_distinct_siblings(sidecars: Any) -> None:
    with pytest.raises(FunctionalWorkflowError):
        FileReferenceInput("a.txt", sidecars)


@pytest.mark.parametrize(
    "data",
    [
        None,
        {"path": "a"},
        {
            "path": "a",
            "sidecars": (),
        },
        {"path": "a", "sidecars": [], "reader": "csv"},
    ],
)
def test_unknown_or_implicit_reference_options_are_rejected(data: object) -> None:
    with pytest.raises(FunctionalWorkflowError):
        FileReferenceInput.from_dict(data)


def test_invalid_file_input_configuration_is_rejected() -> None:
    config = _configuration()
    for refs in (
        [("snapshot_path", FileReferenceInput("a"))],
        (("snapshot_path", "a"),),
        (("candidate", FileReferenceInput("a")),),
        (("bad-name", FileReferenceInput("a")),),
    ):
        with pytest.raises(FunctionalWorkflowError):
            replace(config, file_inputs=refs)  # type: ignore[arg-type]
    data: Any = config.to_dict()
    data["file_inputs"] = []
    with pytest.raises(FunctionalWorkflowError):
        FunctionalWorkflowConfiguration.from_dict(data)
    data.pop("file_inputs")
    with pytest.raises(FunctionalWorkflowError):
        FunctionalWorkflowConfiguration.from_dict(data)


def test_schema_14_can_keep_legacy_json_inputs_without_file_references() -> None:
    config = load_functional_workflow_configuration(
        ROOT / "examples/functional_package/workflow.json"
    )
    config = replace(config, schema_version="1.4")
    plan = plan_functional_workflow_path(
        ROOT / "examples/functional_package/src/example_ml/workflow.py", config, project_root=ROOT
    )
    assert json.loads(plan.to_json())["file_inputs"] == []
    assert FunctionalWorkflowConfiguration.from_dict(config.to_dict()) == config


def test_inventory_contains_raw_hashes_and_no_domain_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capture, "_CHUNK_BYTES", 2)
    config = _configuration()
    plan = plan_functional_workflow_path(SOURCE, config, project_root=ROOT)
    data = json.loads(plan.to_json())
    assert data["schema_version"] == "1.3"
    assert data["ordering"]["policy"] == "source_order"
    assert len(plan.order_after) == 1
    assert len(data["file_inputs"]) == 2
    for inventory in data["file_inputs"]:
        assert inventory["validation_status"] == "hashed_not_loaded"
        assert inventory["domain_status"] == "not_verified"
        for item in inventory["files"]:
            raw = (ROOT / item["path"]).read_bytes()
            assert item["sha256"] == hashlib.sha256(raw).hexdigest()
            assert item["size_bytes"] == len(raw)
    assert len(plan.file_inputs[0].files) == 2


def test_rendered_catalog_passes_paths_and_copies_exact_sibling_names() -> None:
    plan = plan_functional_workflow_path(SOURCE, _configuration(), project_root=ROOT)
    files, copies = render_functional_workflow(plan, root=ROOT, package_name="reviewed")
    catalog = json.loads(files[Path("conf/base/catalog.yml")])
    assert catalog["snapshot_path"] == {
        "type": "MemoryDataset",
        "copy_mode": "assign",
        "data": "data/01_raw/snapshot_path/measurements.txt",
    }
    assert catalog["protocol_path"]["data"] == "data/01_raw/protocol_path/study.json"
    mapping = {target.as_posix(): source for source, target in copies}
    assert (
        mapping["data/01_raw/snapshot_path/measurements.metadata.json"].read_bytes()
        == (EXAMPLE / "data/measurements.metadata.json").read_bytes()
    )
    manifest = json.loads(files[Path("functional-workflow.json")])
    assert manifest["file_reference_destinations"][0]["runtime_hash_validation"] == "not_performed"
    gaps = json.loads(files[Path("regression-coverage.json")])
    assert gaps["missing_file_fixtures"] == ["snapshot_path", "protocol_path"]
    assert "not supported" in files[Path("TESTING.md")]
    assert not any(path.parts[0] == "tests" for path in files)


def test_json_value_and_file_reference_inputs_can_coexist(
    workspace: tuple[Path, FunctionalWorkflowConfiguration], tmp_path: Path
) -> None:
    source, config = workspace
    (tmp_path / "candidate.json").write_text('{"bias": 0.5}')
    config = replace(config, inputs=(("candidate", "candidate.json"),), parameters=())
    plan = plan_functional_workflow_path(source, config, project_root=tmp_path)
    files, copies = render_functional_workflow(plan, root=tmp_path, package_name="mixed")
    catalog = json.loads(files[Path("conf/base/catalog.yml")])
    assert catalog["candidate"]["type"] == "json.JSONDataset"
    assert any(target == Path("data/01_raw/candidate.json") for _, target in copies)
    with pytest.raises(FunctionalWorkflowError, match="disjoint"):
        replace(config, inputs=(("snapshot_path", "candidate.json"),))


@pytest.mark.parametrize("change", ["primary", "sidecar", "missing", "directory", "limit"])
def test_invalid_or_changed_inputs_block_before_publication(
    workspace: tuple[Path, FunctionalWorkflowConfiguration],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    source, config = workspace
    plan = plan_functional_workflow_path(source, config, project_root=tmp_path)
    if change == "limit":
        monkeypatch.setattr(capture, "MAX_REFERENCE_BYTES", 1)
    else:
        path = (
            tmp_path
            / "example/data"
            / ("measurements.txt" if change == "primary" else "measurements.metadata.json")
        )
        if change in {"missing", "directory"}:
            path.unlink()
            if change == "directory":
                path.mkdir()
        else:
            path.write_text("changed")
    with pytest.raises(FunctionalWorkflowError):
        render_functional_workflow(plan, root=tmp_path, package_name="blocked")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("kind", ["link", "reparse", "special"])
def test_links_reparse_and_special_files_are_rejected(
    workspace: tuple[Path, FunctionalWorkflowConfiguration],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    source, config = workspace
    target = tmp_path / "example/data/measurements.txt"
    original = Path.lstat

    def lstat(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path == target:
            return SimpleNamespace(
                st_mode={"link": stat.S_IFLNK, "reparse": stat.S_IFREG, "special": stat.S_IFIFO}[
                    kind
                ],
                st_file_attributes=0x400 if kind == "reparse" else 0,
            )
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(FunctionalWorkflowError):
        generate_functional_kedro_project(source, config, tmp_path / "out", project_root=tmp_path)
    assert not (tmp_path / "out").exists()


def test_resolved_file_escape_is_rejected(
    workspace: tuple[Path, FunctionalWorkflowConfiguration],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, config = workspace
    original = Path.resolve
    target = tmp_path / "example/data/measurements.txt"

    def resolve(path: Path, *args: Any, **kwargs: Any) -> Path:
        return tmp_path.parent if path == target else original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(FunctionalWorkflowError, match="contained"):
        generate_functional_kedro_project(source, config, tmp_path / "out", project_root=tmp_path)


def test_total_byte_limit_includes_all_files(monkeypatch: pytest.MonkeyPatch) -> None:
    # Each file fits individually; the combined snapshot/sidecar/protocol budget does not.
    config = _configuration()
    biggest = max(
        (ROOT / path).stat().st_size
        for _, value in config.file_inputs
        for path in (value.path, *value.sidecars)
    )
    monkeypatch.setattr(capture, "MAX_REFERENCE_BYTES", biggest)
    with pytest.raises(FunctionalWorkflowError, match="in total"):
        plan_functional_workflow_path(SOURCE, config, project_root=ROOT)


def test_inventory_binding_and_metadata_tampering_are_rejected() -> None:
    config = _configuration()
    plan = plan_functional_workflow_path(SOURCE, config, project_root=ROOT)
    with pytest.raises(FunctionalWorkflowError, match="matching captured"):
        plan_functional_workflow(plan.analysis, config, source_package=plan.source_package)
    inventory = plan.file_inputs[0]
    bad = replace(
        inventory, files=(replace(inventory.files[0], sha256="0" * 64), *inventory.files[1:])
    )
    with pytest.raises(FunctionalWorkflowError, match="differ from the captured"):
        render_functional_workflow(
            replace(plan, file_inputs=(bad, *plan.file_inputs[1:])), root=ROOT, package_name="bad"
        )


def test_json_regression_contracts_do_not_invent_file_fixtures(
    workspace: tuple[Path, FunctionalWorkflowConfiguration], tmp_path: Path
) -> None:
    source, config = workspace
    contract = load_workflow_regression_contract(
        ROOT / "examples/functional_package/regression.json"
    )
    with pytest.raises(WorkflowRegressionError, match="file-reference fixtures"):
        generate_functional_kedro_project(
            source, config, tmp_path / "out", project_root=tmp_path, regression_contract=contract
        )
    assert not (tmp_path / "out").exists()


def test_generation_is_compile_only_and_does_not_decode_binary_inputs(
    workspace: tuple[Path, FunctionalWorkflowConfiguration], tmp_path: Path
) -> None:
    source, config = workspace
    data = tmp_path / "example/data/measurements.txt"
    data.write_bytes(b"\xff\x00\xfe")
    marker = tmp_path / "marker"
    (source.parent / "__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
    )
    output = tmp_path / "out"
    paths = generate_functional_kedro_project(source, config, output, project_root=tmp_path)
    assert output / "functional-workflow.json" in paths
    assert (output / "data/01_raw/snapshot_path/measurements.txt").read_bytes() == b"\xff\x00\xfe"
    assert not marker.exists()
    with pytest.raises(ProjectGenerationError, match="already exists"):
        generate_functional_kedro_project(source, config, output, project_root=tmp_path)

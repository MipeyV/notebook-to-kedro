"""Declared orchestration stays separate from observed source and execution approval."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest

from notebook_to_kedro import (
    WorkflowCall,
    WorkflowPreparationDefinition,
    analyze_functional_blocks_path,
    load_workflow_preparation_definition,
    prepare_functional_workflow,
    render_workflow_preparation,
)
from notebook_to_kedro.cli import main
from notebook_to_kedro.exceptions import FunctionalWorkflowError, ProjectGenerationError
from notebook_to_kedro.generation import workflow_preparation as preparation

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples/functional_package"
SOURCE = EXAMPLE / "src/example_ml/transforms.py"


def _definition() -> WorkflowPreparationDefinition:
    return load_workflow_preparation_definition(EXAMPLE / "preparation.json")


@pytest.fixture
def local_package(tmp_path: Path) -> tuple[Path, WorkflowPreparationDefinition]:
    shutil.copytree(EXAMPLE / "src", tmp_path / "src")
    return tmp_path / "src/example_ml/transforms.py", replace(
        _definition(), source_package="src/example_ml"
    )


def test_preview_separates_original_facts_and_new_proposal_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(ROOT)
    files, copies = render_workflow_preparation(SOURCE, _definition())
    report = json.loads(files[Path("workflow-preparation.json")])
    assert report["status"] == "unreviewed_proposal"
    assert report["execution_status"] == "not_run"
    assert report["persistent_io_status"] == report["artifact_policy_status"] == "not_defined"
    assert {block["name"] for block in report["source_facts"]["blocks"]} == {
        "prepare_value",
        "finish_value",
    }
    assert "prepared_workflow" in {
        block["name"] for block in report["proposal"]["analysis"]["blocks"]
    }
    assert (
        report["source_facts"]["sources"][0]["document_sha256"]
        == hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    )
    assert report["source_facts"]["package_module"] == "example_ml.transforms"
    proposed = report["proposal"]
    assert proposed["analysis"]["package_module"] == "example_ml.workflow_adapter"
    assert proposed["ordering_policy"] == "source_order"
    assert proposed["argument_policy"] == "single_use"
    assert proposed["steps"][0]["span"]["unit_id"] == "prepared_module"
    code = files[Path(proposed["adapter"])]
    assert hashlib.sha256(code.encode()).hexdigest() == proposed["sha256"]
    assert "return _original_prepare_value(values=values, scale=scale)" in code
    assert all(item["module"] == "example_ml.transforms" for item in proposed["source_bindings"])
    assert len(copies) == len(report["source_package"]["files"])
    assert not (EXAMPLE / "src/example_ml/workflow_adapter.py").exists()
    assert not any(
        path.name in {"catalog.yml", "parameters.yml", "pyproject.toml"} for path in files
    )


def test_publish_is_a_new_byte_faithful_copy_with_no_overwrite(
    local_package: tuple[Path, WorkflowPreparationDefinition],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, definition = local_package
    monkeypatch.chdir(tmp_path)
    files, copies = render_workflow_preparation(source, definition, project_root=tmp_path)
    original = {path: path.read_bytes() for path, _ in copies}
    destination = tmp_path / "prepared"
    paths = prepare_functional_workflow(source, definition, destination)
    assert len(paths) == len(files) + len(copies)
    for path, text in files.items():
        assert (destination / path).read_bytes() == text.encode()
    for path, target in copies:
        assert (destination / target).read_bytes() == original[path] == path.read_bytes()
    with pytest.raises(ProjectGenerationError, match="already exists"):
        prepare_functional_workflow(source, definition, destination, project_root=tmp_path)


@pytest.mark.parametrize("destination", ["src/example_ml/new", "src/example_ml", "."])
def test_original_package_cannot_be_a_preparation_destination(
    local_package: tuple[Path, WorkflowPreparationDefinition], tmp_path: Path, destination: str
) -> None:
    source, definition = local_package
    with pytest.raises(FunctionalWorkflowError, match="overlaps"):
        prepare_functional_workflow(
            source, definition, tmp_path / destination, project_root=tmp_path
        )
    assert not (tmp_path / "src/example_ml/workflow_adapter.py").exists()


def test_adapter_target_collision_is_rejected(
    local_package: tuple[Path, WorkflowPreparationDefinition], tmp_path: Path
) -> None:
    source, definition = local_package
    (source.parent / "workflow_adapter.py").write_text('"""Existing user code."""\n')
    with pytest.raises(ProjectGenerationError, match="overlap"):
        prepare_functional_workflow(
            source, definition, tmp_path / "prepared", project_root=tmp_path
        )
    assert not (tmp_path / "prepared").exists()


@pytest.mark.parametrize("entrypoint", ["prepare_value", "finish_value"])
def test_existing_functions_cannot_be_replaced(entrypoint: str) -> None:
    with pytest.raises(FunctionalWorkflowError, match="collides"):
        render_workflow_preparation(
            SOURCE, replace(_definition(), entrypoint=entrypoint), project_root=ROOT
        )


def test_unknown_source_function_is_not_invented() -> None:
    definition = replace(_definition(), calls=(WorkflowCall("missing", (), "total"),))
    with pytest.raises(FunctionalWorkflowError, match="no observed source function"):
        render_workflow_preparation(SOURCE, definition, project_root=ROOT)


@pytest.mark.parametrize(
    "change", ["missing_argument", "unbound", "reuse", "earlier_return", "reassign", "shadow"]
)
def test_declared_calls_reuse_shared_signature_binding_and_single_use_guards(change: str) -> None:
    definition = _definition()
    first, second = definition.calls
    if change == "missing_argument":
        definition = replace(
            definition, calls=(replace(first, arguments=(("values", "values"),)), second)
        )
    elif change == "unbound":
        definition = replace(
            definition,
            calls=(replace(first, arguments=(("values", "missing"), ("scale", "scale"))), second),
        )
    elif change == "reuse":
        definition = replace(definition, calls=(first, replace(first, output="total")))
    elif change == "earlier_return":
        definition = replace(definition, output="prepared")
    elif change == "reassign":
        definition = replace(
            definition,
            calls=(
                replace(first, output="values"),
                replace(second, arguments=(("prepared", "values"),)),
            ),
        )
    else:
        definition = replace(definition, arguments=("prepare_value", "scale"))
    with pytest.raises(FunctionalWorkflowError):
        render_workflow_preparation(SOURCE, definition, project_root=ROOT)


def test_no_source_execution_even_with_import_effects_or_unavailable_dependencies(
    tmp_path: Path,
) -> None:
    package = tmp_path / "local_ml"
    package.mkdir()
    marker = tmp_path / "marker"
    (package / "__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
    )
    source = package / "nodes.py"
    source.write_text("import unavailable_preparation_dependency\n\ndef start():\n    return 3\n")
    definition = WorkflowPreparationDefinition(
        "local_ml", "workflow", (), (WorkflowCall("start", (), "result"),), "result"
    )
    files, _ = render_workflow_preparation(source, definition, project_root=tmp_path)
    assert "def workflow():" in files[Path("src/local_ml/workflow_adapter.py")]
    assert not marker.exists()


def test_unsupported_selected_source_blocks_preparation(
    local_package: tuple[Path, WorkflowPreparationDefinition], tmp_path: Path
) -> None:
    source, definition = local_package
    source.write_text("class Uninspected:\n    pass\n")
    with pytest.raises(FunctionalWorkflowError, match="complete selected-module"):
        render_workflow_preparation(source, definition, project_root=tmp_path)


@pytest.mark.parametrize("drift", ["selected", "resource"])
def test_capture_drift_is_rejected_before_any_publication(
    local_package: tuple[Path, WorkflowPreparationDefinition],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    source, definition = local_package
    original = analyze_functional_blocks_path

    def inspect(path: str | Path, **kwargs: Any) -> Any:
        if drift == "selected":
            source.write_bytes(source.read_bytes() + b"\n# changed\n")
        else:
            (source.parent / "assets/offset.json").write_text("0.5\n")
        return original(path, **kwargs)

    monkeypatch.setattr(preparation, "analyze_functional_blocks_path", inspect)
    with pytest.raises(FunctionalWorkflowError, match="differs from the captured"):
        prepare_functional_workflow(
            source, definition, tmp_path / "prepared", project_root=tmp_path
        )
    assert not (tmp_path / "prepared").exists()


def test_definition_is_immutable_and_exports_independent_values() -> None:
    definition = _definition()
    exported: Any = definition.to_dict()
    exported["calls"][0]["arguments"]["values"] = "changed"
    exported["arguments"].append("changed")
    assert definition == _definition()
    assert WorkflowPreparationDefinition.from_dict(definition.to_dict()) == definition
    with pytest.raises(FrozenInstanceError):
        definition.entrypoint = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "2.0"),
        ("source_package", None),
        ("source_package", ""),
        ("source_package", "/tmp/pkg"),
        ("source_package", "../pkg"),
        ("source_package", "pkg/./src"),
        ("source_package", "pkg\\src"),
        ("source_package", "C:pkg"),
        ("entrypoint", "exec(code)"),
        ("output", "_hidden"),
        ("arguments", ["a"]),
        ("arguments", ("x", "x")),
        ("arguments", ("bad-name",)),
        ("arguments", tuple(f"arg_{i}" for i in range(65))),
        ("calls", []),
        ("calls", ()),
        ("calls", ("not a call",)),
        ("calls", (WorkflowCall("start", (), "result"),) * 65),
    ],
)
def test_invalid_direct_definition_is_rejected(field: str, value: Any) -> None:
    with pytest.raises(FunctionalWorkflowError):
        replace(_definition(), **{field: value})


@pytest.mark.parametrize(
    "arguments",
    [
        [("x", "x")],
        ("bad",),
        (("x",),),
        (("x", "x", "x"),),
        (("x", "bad-name"),),
        (("x", "x"), ("x", "y")),
        tuple((f"arg_{i}", "x") for i in range(65)),
    ],
)
def test_invalid_call_arguments_are_rejected(arguments: Any) -> None:
    with pytest.raises(FunctionalWorkflowError):
        WorkflowCall("call", arguments, "result")


@pytest.mark.parametrize(("function", "output"), [("bad.name", "result"), ("call", "parameters")])
def test_invalid_call_names_are_rejected(function: str, output: str) -> None:
    with pytest.raises(FunctionalWorkflowError):
        WorkflowCall(function, (), output)


@pytest.mark.parametrize(
    "change",
    ["not_mapping", "unknown", "arguments", "calls", "call_type", "call_fields", "call_arguments"],
)
def test_malformed_json_shapes_are_rejected(change: str) -> None:
    data: Any = _definition().to_dict()
    if change == "not_mapping":
        data = []
    elif change == "unknown":
        data["unknown"] = True
    elif change == "arguments":
        data["arguments"] = "values"
    elif change == "calls":
        data["calls"] = {}
    elif change == "call_type":
        data["calls"] = [None]
    elif change == "call_fields":
        data["calls"][0]["unknown"] = True
    else:
        data["calls"][0]["arguments"] = []
    with pytest.raises(FunctionalWorkflowError):
        WorkflowPreparationDefinition.from_dict(data)


@pytest.mark.parametrize(
    "content",
    [b"{", b"\xff", b" " * 65_537, b'{"schema_version":"1.0","schema_version":"1.0"}', b"[" * 2000],
    ids=["syntax", "encoding", "size", "duplicate", "depth"],
)
def test_loader_rejects_invalid_encoding_size_json_and_duplicates(
    tmp_path: Path, content: bytes
) -> None:
    path = tmp_path / "definition.json"
    path.write_bytes(content)
    with pytest.raises(FunctionalWorkflowError):
        load_workflow_preparation_definition(path)


def test_loader_reports_missing_files(tmp_path: Path) -> None:
    with pytest.raises(FunctionalWorkflowError, match="Cannot read preparation"):
        load_workflow_preparation_definition(tmp_path / "absent.json")


def test_cli_preview_and_explicit_publication(
    local_package: tuple[Path, WorkflowPreparationDefinition],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source, definition = local_package
    path = tmp_path / "definition.json"
    path.write_text(json.dumps(definition.to_dict()))
    arguments = ["prepare-workflow", str(source), str(path), "--project-root", str(tmp_path)]
    assert main(arguments) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["publication_status"] == "not_written"
    assert preview["manifest"]["status"] == "unreviewed_proposal"
    assert "def prepared_workflow" in preview["adapter_source"]
    assert "src/example_ml/assets/offset.json" in preview["copy_targets"]
    destination = tmp_path / "prepared"
    assert not destination.exists()
    assert main([*arguments, "--output-dir", str(destination)]) == 0
    published = json.loads(capsys.readouterr().out)
    assert published["publication_status"] == "review_copy_written"
    assert published["status"] == "unreviewed_proposal"
    assert published["execution_status"] == "not_run"
    assert (destination / "workflow-preparation.json").is_file()
    assert main([*arguments, "--output-dir", str(destination)]) == 1
    assert "already exists" in capsys.readouterr().err

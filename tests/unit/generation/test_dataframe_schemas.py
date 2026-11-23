"""Bounded frame metadata contracts preserve source/data and reject incompatible boundaries."""

from __future__ import annotations

import ast
import builtins
import hashlib
import importlib
import inspect
import json
import sys
import typing
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from notebook_to_kedro import (
    DataFrameSchema,
    GenerateRequest,
    LocalProjectConfiguration,
    NotebookTypeContract,
    PlanRequest,
    analyze_notebook_path,
    generate_kedro_project,
    load_local_project_configuration,
    load_notebook_type_contract,
    plan_notebook_path,
    run_local_operation,
)
from notebook_to_kedro.exceptions import LocalOperationError, ProjectGenerationError
from notebook_to_kedro.generation.kedro.dataframe_checks import SCHEMA_CHECK_EXTENSION
from notebook_to_kedro.generation.kedro.dataframe_schema import MAX_FRAME_COLUMNS, MAX_FRAME_SCHEMAS
from notebook_to_kedro.generation.kedro.generator import render_kedro_project
from notebook_to_kedro.generation.kedro.node_type_checks import RUNTIME_CHECK_SOURCE


class MetadataString(str):
    pass


def _runtime() -> dict[str, Any]:
    namespace: dict[str, Any] = {"__name__": "schema_runtime"}
    exec(
        compile(
            RUNTIME_CHECK_SOURCE + SCHEMA_CHECK_EXTENSION, "runtime.py", "exec", dont_inherit=True
        ),
        namespace,
    )
    return namespace


def _frame() -> Any:
    pd = importlib.import_module("pandas")
    return pd.DataFrame(
        {"x": pd.Series([1.5, 2.5], dtype="float64"), "y": pd.Series([1, 2], dtype="int64")}
    )


def _schema() -> DataFrameSchema:
    return DataFrameSchema((("x", "float64"), ("y", "int64")))


def _decorate(
    schema: DataFrameSchema, business: Any, *, inputs: bool = True, outputs: bool = True
) -> Any:
    pd = importlib.import_module("pandas")
    spec = ("frame", schema.columns, schema.allow_extra_columns)
    cls = ("frame", "pandas.DataFrame", pd.DataFrame)
    return _runtime()["validate_frame_node"](
        task_id="frame-task",
        inputs={"frame": cls} if inputs else {},
        outputs=(cls,) if outputs else (),
        input_frames={"frame": spec} if inputs else {},
        output_frames=(spec,) if outputs else (),
    )(business)


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "workflow.ipynb"
    source.write_text(
        json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {"language_info": {"name": "python"}},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": f"cell-{i}",
                        "metadata": {},
                        "execution_count": None,
                        "outputs": [],
                        "source": code,
                    }
                    for i, code in enumerate(
                        (
                            "import pandas as pd",
                            "frame = pd.DataFrame({'x': [1.5, 2.5], 'y': [1, 2]})",
                            "copy = frame.copy()",
                            "output = copy.copy()",
                        )
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    return source


def _contract(source: Path) -> NotebookTypeContract:
    return NotebookTypeContract(
        hashlib.sha256(source.read_bytes()).hexdigest(),
        (
            ("frame", "pandas.DataFrame"),
            ("copy", "pandas.DataFrame"),
            ("output", "pandas.DataFrame"),
        ),
        "1.1",
        (("frame", _schema()), ("output", _schema())),
    )


def _module(files: dict[Path, str], monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    package = ModuleType("frame_project")
    package.__dict__["__path__"] = []
    helper = ModuleType("frame_project._node_type_validation")
    nodes = ModuleType("frame_project.nodes")
    for module in (package, helper, nodes):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(
        compile(
            files[Path("src/frame_project/_node_type_validation.py")],
            "helper.py",
            "exec",
            dont_inherit=True,
        ),
        helper.__dict__,
    )
    code = next(text for path, text in files.items() if path.name == "nodes.py")
    exec(compile(code, "nodes.py", "exec", dont_inherit=True), nodes.__dict__)
    return nodes


def test_versioned_json_and_direct_contracts_preserve_order_and_immutability(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    contract = _contract(source)
    exported = contract.to_dict()
    path = tmp_path / "types.json"
    path.write_text(json.dumps(exported, sort_keys=True), encoding="utf-8")
    assert load_notebook_type_contract(path) == contract
    assert contract.dataframes[0][1].columns == (("x", "float64"), ("y", "int64"))
    dynamic: Any = contract.dataframes[0][1]
    with pytest.raises(FrozenInstanceError):
        dynamic.allow_extra_columns = True
    exported["dataframes"] = {}
    assert contract.to_dict()["dataframes"]
    plain = replace(contract, schema_version="1.0", dataframes=())
    assert "dataframes" not in plain.to_dict()


@pytest.mark.parametrize(
    "columns",
    [
        [],
        (),
        ("bad",),
        (("x",),),
        ((1, "int64"),),
        (("", "int64"),),
        (("x" * 129, "int64"),),
        (("x\n", "int64"),),
        (("x", "int64"), ("x", "float64")),
        (("x", None),),
        (("x", []),),
        (("x", "__import__('os')"),),
        (("x", "float"),),
        tuple((f"v{i}", "int64") for i in range(MAX_FRAME_COLUMNS + 1)),
    ],
    ids=lambda value: str(value)[:50],
)
def test_invalid_direct_column_schemas_are_rejected(columns: Any) -> None:
    with pytest.raises(ProjectGenerationError):
        DataFrameSchema(columns)


@pytest.mark.parametrize("policy", [1, "true", None, []])
def test_extra_column_policy_is_a_real_boolean(policy: Any) -> None:
    with pytest.raises(ProjectGenerationError):
        DataFrameSchema((("x", "int64"),), policy)


def test_metadata_uses_plain_immutable_python_primitives() -> None:
    for columns in (((MetadataString("x"), "int64"),), (("x", MetadataString("int64")),)):
        with pytest.raises(ProjectGenerationError):
            DataFrameSchema(columns)


@pytest.mark.parametrize(
    "frames",
    [
        [],
        (),
        ("bad",),
        (("frame",),),
        ((1, _schema()),),
        (("missing", _schema()),),
        (("frame", {}),),
        (("frame", _schema()), ("frame", _schema())),
    ],
    ids=lambda value: str(value)[:60],
)
def test_invalid_parent_frame_bindings_are_rejected(frames: Any) -> None:
    with pytest.raises(ProjectGenerationError):
        NotebookTypeContract("a" * 64, (("frame", "pandas.DataFrame"),), "1.1", frames)


def test_frame_schemas_require_matching_dataframe_declarations_and_version() -> None:
    frames = (("frame", _schema()),)
    for label, version in (("int", "1.1"), ("pandas.Series", "1.1"), ("pandas.DataFrame", "1.0")):
        with pytest.raises(ProjectGenerationError):
            NotebookTypeContract("a" * 64, (("frame", label),), version, frames)
    too_many = tuple((f"v{i}", _schema()) for i in range(MAX_FRAME_SCHEMAS + 1))
    with pytest.raises(ProjectGenerationError):
        NotebookTypeContract(
            "a" * 64, tuple((name, "pandas.DataFrame") for name, _ in too_many), "1.1", too_many
        )


@pytest.mark.parametrize(
    "frames",
    [
        None,
        [],
        {},
        {"frame": None},
        {"frame": {}},
        {"frame": {"columns": {}}},
        {"frame": {"columns": [], "unknown": True}},
        {"frame": {"columns": [None]}},
        {"frame": {"columns": [{"name": "x"}]}},
        {"frame": {"columns": [{"name": "x", "dtype": "int64", "extra": 1}]}},
        {"frame": {"columns": [{"name": "x", "dtype": "int64"}], "allow_extra_columns": "false"}},
    ],
    ids=lambda value: str(value)[:60],
)
def test_malformed_frame_json_is_rejected(tmp_path: Path, frames: Any) -> None:
    path = tmp_path / "types.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "source_sha256": "a" * 64,
                "datasets": {"frame": "pandas.DataFrame"},
                "dataframes": frames,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ProjectGenerationError):
        load_notebook_type_contract(path)


def test_size_budget_includes_frame_metadata_and_column_limits_are_bounded() -> None:
    valid = DataFrameSchema(tuple((f"c{i}", "int64") for i in range(MAX_FRAME_COLUMNS)))
    assert len(valid.columns) == MAX_FRAME_COLUMNS
    frames = tuple((f"v{i}", _schema()) for i in range(MAX_FRAME_SCHEMAS))
    boundary = NotebookTypeContract(
        "a" * 64, tuple((name, "pandas.DataFrame") for name, _ in frames), "1.1", frames
    )
    assert len(boundary.dataframes) == MAX_FRAME_SCHEMAS
    huge = DataFrameSchema(
        tuple((f"v{i:03}" + "漢" * 124, "float64") for i in range(MAX_FRAME_COLUMNS))
    )
    with pytest.raises(ProjectGenerationError, match="64 KiB"):
        NotebookTypeContract("a" * 64, (("frame", "pandas.DataFrame"),), "1.1", (("frame", huge),))


def test_metadata_checks_preserve_identity_and_do_not_inspect_row_values_or_index() -> None:
    frame = _frame()
    frame.index = [7, 7]
    frame.loc[7, "x"] = float("nan")
    snapshot = frame.copy(deep=True)
    checked = _decorate(_schema(), lambda frame: frame)
    assert checked(frame) is frame
    importlib.import_module("pandas").testing.assert_frame_equal(frame, snapshot)
    with pytest.raises(TypeError, match="NTV001"):
        checked([])


def test_empty_frames_that_satisfy_metadata_preserve_source_assertions_and_errors() -> None:
    pd = importlib.import_module("pandas")
    empty = pd.DataFrame({"x": pd.Series(dtype="float64"), "y": pd.Series(dtype="int64")})

    def source(frame: Any) -> Any:
        assert not frame.empty, "Original empty-data check"
        return frame

    with pytest.raises(AssertionError, match="Original empty-data check"):
        _decorate(_schema(), source)(empty)
    original = ValueError("Original business error")

    def failing(frame: Any) -> Any:
        assert frame is empty
        raise original

    with pytest.raises(ValueError, match="Original business error") as caught:
        _decorate(_schema(), failing)(empty)
    assert caught.value is original


@pytest.mark.parametrize(
    "problem", ["missing", "extra", "order", "duplicate", "integer", "multiindex", "dtype"]
)
def test_input_schema_mismatch_precedes_source_without_repair(problem: str) -> None:
    pd = importlib.import_module("pandas")
    frame = _frame()
    if problem == "missing":
        frame = frame.drop(columns="x")
    elif problem == "extra":
        frame["extra"] = 1
    elif problem == "order":
        frame = frame[["y", "x"]]
    elif problem == "duplicate":
        frame.columns = ["x", "x"]
    elif problem == "integer":
        frame.columns = [0, 1]
    elif problem == "multiindex":
        frame.columns = pd.MultiIndex.from_tuples([("x", "a"), ("y", "b")])
    else:
        frame["x"] = frame["x"].astype("float32")
    snapshot = frame.copy(deep=True)
    calls = []

    def business(frame: Any) -> Any:
        calls.append("called")
        return frame

    checked = _decorate(_schema(), business)
    with pytest.raises(ValueError, match="NVS001 frame-task input frame"):
        checked(frame)
    assert not calls
    pd.testing.assert_frame_equal(frame, snapshot)


def test_allowed_extra_columns_keep_declared_relative_order_and_dtype_checks() -> None:
    frame = _frame()
    frame.insert(1, "untyped", [object(), None])
    checked = _decorate(replace(_schema(), allow_extra_columns=True), lambda frame: frame)
    assert checked(frame) is frame
    with pytest.raises(ValueError, match="column order"):
        checked(frame[["y", "untyped", "x"]])
    wrong = frame.copy()
    wrong["y"] = wrong["y"].astype("float64")
    with pytest.raises(ValueError, match="expected dtype int64"):
        checked(wrong)


def test_output_schema_mismatch_and_class_errors_are_separate_and_do_not_roll_back() -> None:
    frame = _frame()
    calls = []

    def business(frame: Any) -> Any:
        calls.append("called")
        return frame.drop(columns="y")

    with pytest.raises(ValueError, match="NVS002 frame-task output frame"):
        _decorate(_schema(), business)(frame)
    assert calls == ["called"]

    def row_count(frame: Any) -> int:
        return len(frame)

    with pytest.raises(TypeError, match="NTV002"):
        _decorate(_schema(), row_count)(frame)


def test_partial_multi_output_schema_slots_and_input_only_schemas() -> None:
    pd = importlib.import_module("pandas")
    frame = _frame()
    sentinel = object()
    result = (sentinel, frame)
    runtime = _runtime()["validate_frame_node"]
    checked = runtime(
        task_id="multi",
        inputs={},
        outputs=(None, ("frame", "pandas.DataFrame", pd.DataFrame)),
        input_frames={},
        output_frames=(None, ("frame", _schema().columns, False)),
    )(lambda: result)
    assert checked() is result
    expected_frame = frame

    def consume(frame: Any) -> None:
        assert frame is expected_frame

    input_only = _decorate(_schema(), consume, outputs=False)
    assert input_only(frame) is None
    output_only = _decorate(_schema(), lambda: frame, inputs=False)
    assert output_only() is frame


def test_nullable_dtypes_and_private_values_do_not_imply_null_or_content_validation() -> None:
    pd = importlib.import_module("pandas")

    class Private:
        def __repr__(self) -> str:
            raise AssertionError("Row values must not be rendered")

    frame = pd.DataFrame(
        {
            "nullable": pd.Series([None], dtype="Int64"),
            "payload": pd.Series([Private()], dtype="object"),
        }
    )
    schema = DataFrameSchema((("nullable", "Int64"), ("payload", "object")))
    assert _decorate(schema, lambda frame: frame)(frame) is frame


def test_generation_binds_schemas_without_importing_pandas_or_executing_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)
    facts, plan = analyze_notebook_path(source), plan_notebook_path(source)
    contract = _contract(source)
    original_import = builtins.__import__

    def guarded(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.split(".", maxsplit=1)[0] in {"pandas", "numpy", "sklearn"}:
            raise AssertionError("Generation imported an ML library")
        return original_import(name, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(builtins, "__import__", guarded)
        files, _ = render_kedro_project(
            plan,
            source_facts=facts,
            node_types=contract,
            enforce_node_types=True,
            package_name="frame_project",
        )
    nodes = _module(files, monkeypatch)
    first, second, third = (getattr(nodes, task.name) for task in plan.task_candidates)
    frame = first()
    copy = second(frame)
    assert third(copy).equals(frame)
    assert typing.get_type_hints(first)["return"] is importlib.import_module("pandas").DataFrame
    assert "ValueError:" in str(inspect.getdoc(first))
    report = json.loads(files[Path("node-types.json")])
    assert report["runtime_checks"]["implementation"] == "node-types-runtime-v2"
    assert report["dataframe_schema_validation"] == "not_run"
    assert report["unschematized_dataframes"] == ["copy"]
    annotation, _ = render_kedro_project(
        plan, source_facts=facts, node_types=contract, package_name="frame_project"
    )
    assert Path("src/frame_project/_node_type_validation.py") not in annotation
    assert "runtime_checks" not in json.loads(annotation[Path("node-types.json")])
    original = ast.parse(next(text for path, text in annotation.items() if path.name == "nodes.py"))
    checked = ast.parse(next(text for path, text in files.items() if path.name == "nodes.py"))
    assert [
        ast.dump(node.body[1:][0]) for node in original.body if isinstance(node, ast.FunctionDef)
    ] == [ast.dump(node.body[1:][0]) for node in checked.body if isinstance(node, ast.FunctionDef)]


def test_local_settings_use_the_same_versioned_contract_and_stale_source_guard(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    path = tmp_path / "types.json"
    path.write_text(json.dumps(_contract(source).to_dict()), encoding="utf-8")
    config = LocalProjectConfiguration(
        tmp_path, source, "notebook", node_types=path, enforce_node_types=True
    )
    settings = tmp_path / "project.json"
    settings.write_text(json.dumps(config.to_dict()), encoding="utf-8")
    assert load_local_project_configuration(settings) == config
    run_local_operation(PlanRequest(config))
    run_local_operation(GenerateRequest(config, Path("project")))
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(LocalOperationError, match="SHA-256"):
        run_local_operation(GenerateRequest(config, Path("blocked")))
    assert not (tmp_path / "blocked").exists()


def test_schema_metadata_does_not_bypass_source_accounting(tmp_path: Path) -> None:
    source = _source(tmp_path)
    facts, plan = analyze_notebook_path(source), plan_notebook_path(source)
    changed = replace(plan.task_candidates[0], source="frame = pd.DataFrame({'wrong': [1]})")
    plan = replace(plan, task_candidates=(changed, *plan.task_candidates[1:]))
    with pytest.raises(ProjectGenerationError, match="SA003"):
        generate_kedro_project(
            plan,
            tmp_path / "blocked",
            source_facts=facts,
            node_types=_contract(source),
            enforce_node_types=True,
        )
    assert not (tmp_path / "blocked").exists()


def test_reassigned_dataframe_versions_have_independent_schemas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)
    notebook = json.loads(source.read_text(encoding="utf-8"))
    notebook["cells"][2]["source"] = "frame = frame.rename(columns={'x': 'z'})"
    notebook["cells"][3]["source"] = "output = frame.copy()"
    source.write_text(json.dumps(notebook), encoding="utf-8")
    facts, plan = analyze_notebook_path(source), plan_notebook_path(source)
    version = "frame__" + plan.task_candidates[1].name
    changed = DataFrameSchema((("z", "float64"), ("y", "int64")))
    contract = NotebookTypeContract(
        facts.notebook.content_sha256,
        (
            ("frame", "pandas.DataFrame"),
            (version, "pandas.DataFrame"),
            ("output", "pandas.DataFrame"),
        ),
        "1.1",
        (("frame", _schema()), (version, changed), ("output", changed)),
    )
    files, _ = render_kedro_project(
        plan,
        source_facts=facts,
        node_types=contract,
        enforce_node_types=True,
        package_name="frame_project",
    )
    nodes = _module(files, monkeypatch)
    first, second, third = (getattr(nodes, task.name) for task in plan.task_candidates)
    old = first()
    new = second(old)
    assert list(old.columns) == ["x", "y"]
    assert list(third(new).columns) == ["z", "y"]

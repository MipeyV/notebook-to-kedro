"""Runtime boundaries reject wrong classes without rewriting source or claiming schema proof."""

from __future__ import annotations

import ast
import builtins
import hashlib
import importlib
import inspect
import json
import sys
import typing
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from notebook_to_kedro import (
    GenerateRequest,
    LocalProjectConfiguration,
    NotebookTypeContract,
    PlanRequest,
    analyze_notebook_path,
    generate_kedro_project,
    load_local_project_configuration,
    plan_notebook_path,
    run_local_operation,
)
from notebook_to_kedro.cli import main
from notebook_to_kedro.exceptions import LocalOperationError, ProjectGenerationError
from notebook_to_kedro.generation.kedro.generator import _PipelineEntry, render_kedro_project
from notebook_to_kedro.generation.kedro.node_type_checks import (
    RUNTIME_CHECK_SOURCE,
    render_type_decorator,
)
from notebook_to_kedro.ir import TaskCandidate


def _runtime() -> dict[str, Any]:
    namespace: dict[str, Any] = {"__name__": "runtime_boundary_test"}
    exec(compile(RUNTIME_CHECK_SOURCE, "runtime.py", "exec", dont_inherit=True), namespace)
    return namespace


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "source.ipynb"
    source.write_text(
        json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {"language_info": {"name": "python"}},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": f"cell-{index}",
                        "metadata": {},
                        "execution_count": None,
                        "outputs": [],
                        "source": code,
                    }
                    for index, code in enumerate(
                        (
                            "value = 3",
                            "result = value + 1",
                            "leaf = result\nassert leaf > 0, 'Expected positive leaf'",
                        )
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    return source


def _contract(source: Path, **datasets: str) -> NotebookTypeContract:
    return NotebookTypeContract(
        hashlib.sha256(source.read_bytes()).hexdigest(), tuple(datasets.items())
    )


def _module(files: dict[Path, str], monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    parent = ModuleType("checked_example")
    parent.__dict__["__path__"] = []
    helper = ModuleType("checked_example._node_type_validation")
    nodes = ModuleType("checked_example.nodes")
    for module in (parent, helper, nodes):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    helper_source = files[Path("src/checked_example/_node_type_validation.py")]
    exec(compile(helper_source, "runtime.py", "exec", dont_inherit=True), helper.__dict__)
    code = next(text for path, text in files.items() if path.name == "nodes.py")
    exec(compile(code, "nodes.py", "exec", dont_inherit=True), nodes.__dict__)
    return nodes


def test_generated_checks_preserve_source_signature_identity_and_assertions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)
    plan, facts = plan_notebook_path(source), analyze_notebook_path(source)
    contract = _contract(source, value="int", result="int", leaf="int")
    plain, _ = render_kedro_project(
        plan, source_facts=facts, node_types=contract, package_name="checked_example"
    )
    files, _ = render_kedro_project(
        plan,
        source_facts=facts,
        node_types=contract,
        enforce_node_types=True,
        package_name="checked_example",
    )
    nodes = _module(files, monkeypatch)
    for task in plan.task_candidates:
        function = getattr(nodes, task.name)
        assert inspect.signature(function) == inspect.signature(function.__wrapped__)
        assert typing.get_type_hints(function)["return"] is int
        assert function.__name__ == task.name
        assert "TypeError:" in str(inspect.getdoc(function))
    first, second, third = (getattr(nodes, task.name) for task in plan.task_candidates)
    assert first() == 3
    assert second(3) == second(value=3) == 4
    with pytest.raises(
        TypeError, match=r"NTV001 .* input value: expected int; received builtins.bool"
    ):
        second(value=True)
    with pytest.raises(AssertionError, match="Expected positive leaf"):
        third(-1)
    original = ast.parse(next(text for path, text in plain.items() if path.name == "nodes.py"))
    checked = ast.parse(next(text for path, text in files.items() if path.name == "nodes.py"))
    original_bodies = [
        ast.dump(ast.Module(body=node.body[1:], type_ignores=[]))
        for node in original.body
        if isinstance(node, ast.FunctionDef)
    ]
    checked_bodies = [
        ast.dump(ast.Module(body=node.body[1:], type_ignores=[]))
        for node in checked.body
        if isinstance(node, ast.FunctionDef)
    ]
    assert original_bodies == checked_bodies
    report = json.loads(files[Path("node-types.json")])
    assert report["runtime_checks"]["checked_tasks"] == [task.id for task in plan.task_candidates]
    assert report["runtime_type_validation"] == "not_run"
    assert report["dataframe_schema_validation"] == "not_supported"
    assert all(
        files[path] == content
        for path, content in plain.items()
        if path.name not in {"nodes.py", "node-types.json"}
    )
    assert "runtime_checks" not in json.loads(plain[Path("node-types.json")])


@pytest.mark.parametrize(
    ("expected", "valid", "invalid"),
    [
        (bool, True, 1),
        (int, 2, True),
        (int, 2, np.int64(2)),
        (float, 2.0, 2),
        (str, "ok", np.str_("ok")),
    ],
)
def test_exact_scalar_checks_run_before_business_code(
    expected: type[object], valid: object, invalid: object
) -> None:
    calls: list[object] = []

    def business(value: object) -> object:
        calls.append(value)
        return value

    check = _runtime()["validate_node"](
        task_id="scalar", inputs={"value": ("data", expected.__name__, expected)}, outputs=()
    )
    checked = check(business)
    assert checked(valid) is valid
    assert calls == [valid]
    with pytest.raises(TypeError, match="NTV001 scalar input data"):
        checked(invalid)
    assert calls == [valid]


def test_object_classes_allow_subclasses_without_schema_or_fitted_state_checks() -> None:
    pd = importlib.import_module("pandas")
    sklearn_base = importlib.import_module("sklearn.base")
    sklearn_pipeline = importlib.import_module("sklearn.pipeline")
    values = [
        (pd.DataFrame, pd.DataFrame({"unreviewed": [None]})),
        (pd.Series, pd.Series([None])),
        (np.ndarray, np.array([None], dtype=object)),
        (sklearn_pipeline.Pipeline, sklearn_pipeline.Pipeline([])),
        (sklearn_base.BaseEstimator, sklearn_pipeline.Pipeline([])),
    ]
    for expected, value in values:
        checked = _runtime()["validate_node"](
            task_id="objects",
            inputs={"value": ("data", "declared", expected)},
            outputs=(("out", "declared", expected),),
        )(lambda value: value)
        assert checked(value) is value
        with pytest.raises(TypeError, match="NTV001 objects input data"):
            checked(object())


def test_output_violations_occur_after_source_without_coercion_or_value_disclosure() -> None:
    class PrivateValue:
        def __repr__(self) -> str:
            raise AssertionError("Values must not be rendered in diagnostics")

    result = PrivateValue()
    calls: list[str] = []

    def business() -> object:
        calls.append("called")
        return result

    checked = _runtime()["validate_node"](
        task_id="producer", inputs={}, outputs=(("score", "float", float),)
    )(business)
    with pytest.raises(TypeError, match="NTV002 producer output score: expected float"):
        checked()
    assert calls == ["called"]


@pytest.mark.parametrize("result", [None, 1, [1, 2], (1,), (1, 2, 3)])
def test_multi_output_arity_errors_are_explicit(result: object) -> None:
    checked = _runtime()["validate_node"](
        task_id="shape", inputs={}, outputs=(("first", "int", int), None)
    )(lambda: result)
    with pytest.raises(TypeError, match="NTV002 shape output: expected tuple of 2 source outputs"):
        checked()


def test_return_identity_partial_slots_and_single_arrays_are_preserved() -> None:
    untouched = object()
    result = (2, untouched, True)
    checked = _runtime()["validate_node"](
        task_id="tuple", inputs={}, outputs=(("first", "int", int), None, ("last", "bool", bool))
    )(lambda: result)
    assert checked() is result
    wrong = _runtime()["validate_node"](
        task_id="tuple", inputs={}, outputs=(None, ("second", "str", str))
    )(lambda: (2, 3))
    with pytest.raises(TypeError, match="NTV002 tuple output second: expected str"):
        wrong()
    array = np.array([1, 2])
    single = _runtime()["validate_node"](
        task_id="array", inputs={}, outputs=(("array", "numpy.ndarray", np.ndarray),)
    )(lambda: array)
    assert single() is array
    untyped = _runtime()["validate_node"](task_id="untyped", inputs={}, outputs=(None, None))(
        lambda: untouched
    )
    assert untyped() is untouched


def test_source_errors_and_bound_declarations_are_preserved() -> None:
    error = ValueError("original")

    def business(value: int) -> int:
        assert value == 1
        raise error

    inputs = {"value": ("value", "int", int)}
    checked = _runtime()["validate_node"](task_id="source", inputs=inputs, outputs=())(business)
    inputs.clear()
    with pytest.raises(TypeError, match="NTV001"):
        checked("wrong")
    with pytest.raises(ValueError, match="original") as caught:
        checked(1)
    assert caught.value is error


def test_untyped_nodes_and_alias_collisions_are_not_silently_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)
    notebook = json.loads(source.read_text(encoding="utf-8"))
    notebook["cells"][0]["source"] = "_ntk_validate = 7\nvalue = 3"
    source.write_text(json.dumps(notebook), encoding="utf-8")
    plan = plan_notebook_path(source)
    files, _ = render_kedro_project(
        plan,
        source_facts=analyze_notebook_path(source),
        node_types=_contract(source, value="int"),
        enforce_node_types=True,
        package_name="checked_example",
    )
    code = next(text for path, text in files.items() if path.name == "nodes.py")
    assert "validate_node as _ntk__validate" in code
    nodes = _module(files, monkeypatch)
    assert not hasattr(getattr(nodes, plan.task_candidates[-1].name), "__wrapped__")
    assert json.loads(files[Path("node-types.json")])["runtime_checks"]["checked_tasks"] == [
        task.id for task in plan.task_candidates[:2]
    ]


def test_input_only_decorator_has_no_return_shape_requirement() -> None:
    task = TaskCandidate("consume", "consume", (), (), ("value",), (), "value")
    entry = _PipelineEntry(task, {"value": "value"}, (), {})
    contract = NotebookTypeContract("a" * 64, (("value", "int"),))
    decorator = render_type_decorator(entry, contract, "_ntk")
    namespace = {"_ntk_validate": _runtime()["validate_node"], "_ntk_builtins": builtins}
    exec(
        compile(
            decorator + "def consume(value):\n    return None\n",
            "node.py",
            "exec",
            dont_inherit=True,
        ),
        namespace,
    )
    assert namespace["consume"](1) is None
    with pytest.raises(TypeError, match="NTV001"):
        namespace["consume"](value=True)


@pytest.mark.parametrize("flag", [True, 1, "true", None, []])
def test_invalid_or_unconfigured_enforcement_refuses_publication(tmp_path: Path, flag: Any) -> None:
    source = _source(tmp_path)
    with pytest.raises(ProjectGenerationError, match="enforce_node_types"):
        generate_kedro_project(
            plan_notebook_path(source),
            tmp_path / "blocked",
            source_facts=analyze_notebook_path(source),
            enforce_node_types=flag,
        )
    assert not (tmp_path / "blocked").exists()


def test_local_settings_cli_and_analysis_remain_static(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)
    types = tmp_path / "types.json"
    types.write_text(
        json.dumps(_contract(source, value="pandas.DataFrame").to_dict()), encoding="utf-8"
    )
    config = LocalProjectConfiguration(
        tmp_path, source, "notebook", node_types=types, enforce_node_types=True
    )
    location = tmp_path / "project.json"
    location.write_text(json.dumps(config.to_dict()), encoding="utf-8")
    assert load_local_project_configuration(location) == config
    original = builtins.__import__

    def guarded(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.split(".", maxsplit=1)[0] in {"pandas", "numpy", "sklearn"}:
            raise AssertionError("Planning imported an application library")
        return original(name, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(builtins, "__import__", guarded)
        preview = run_local_operation(PlanRequest(config)).to_dict()
    assert preview["execution_status"] == "not_run"
    run_local_operation(GenerateRequest(config, Path("published")))
    assert (tmp_path / "published/src/generated_project/_node_type_validation.py").is_file()
    assert (
        main(
            [
                "generate",
                str(source),
                str(tmp_path / "cli"),
                "--node-types",
                str(types),
                "--enforce-node-types",
            ]
        )
        == 0
    )
    assert "Created Kedro project" in capsys.readouterr().out
    assert main(["generate", str(source), str(tmp_path / "blocked"), "--enforce-node-types"]) == 1
    assert "enforce_node_types" in capsys.readouterr().err
    for value in (1, "true", None):
        with pytest.raises(LocalOperationError, match="enforce_node_types"):
            replace(config, enforce_node_types=typing.cast("Any", value))
    with pytest.raises(LocalOperationError, match="enforce_node_types"):
        replace(config, node_types=None)
    assert "enforce_node_types" not in replace(config, enforce_node_types=False).to_dict()

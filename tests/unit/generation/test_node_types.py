"""Explicit dataset types bind to source/graph identities without executing ML code."""

from __future__ import annotations

import ast
import builtins
import hashlib
import importlib
import json
import typing
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from notebook_to_kedro import (
    GenerateRequest,
    InspectRequest,
    LocalProjectConfiguration,
    NotebookTypeContract,
    PlanningResult,
    PlanRequest,
    analyze_notebook_path,
    generate_kedro_project,
    load_local_project_configuration,
    load_notebook_type_contract,
    measure_local_operation,
    plan_notebook_path,
    run_local_operation,
)
from notebook_to_kedro.cli import main
from notebook_to_kedro.exceptions import LocalOperationError, ProjectGenerationError
from notebook_to_kedro.generation.kedro import render_node_function
from notebook_to_kedro.generation.kedro.generator import render_kedro_project
from notebook_to_kedro.generation.kedro.node_types import MAX_DATASET_TYPES, MAX_NODE_TYPE_BYTES
from notebook_to_kedro.generation.kedro.profiles import KedroArchitectureProfile


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
                            "result = result * 2",
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


def _nodes(files: dict[Path, str]) -> tuple[str, dict[str, ast.FunctionDef]]:
    code = next(text for path, text in files.items() if path.name == "nodes.py")
    functions = {
        node.name: node for node in ast.parse(code).body if isinstance(node, ast.FunctionDef)
    }
    return code, functions


def test_redefinitions_bind_dataset_versions_and_preserve_body_and_default_output(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    facts, plan = analyze_notebook_path(source), plan_notebook_path(source)
    plain, _ = render_kedro_project(plan, source_facts=facts)
    old_result = plan.task_candidates[2].name
    contract = _contract(source, value="int", result="int", **{f"result__{old_result}": "str"})
    snapshot = facts.to_json()
    typed, copies = render_kedro_project(plan, source_facts=facts, node_types=contract)
    assert not copies
    assert facts.to_json() == snapshot
    assert all(typed[path] == text for path, text in plain.items() if path.name != "nodes.py")
    code, functions = _nodes(typed)
    namespace: dict[str, Any] = {}
    exec(compile(code, "nodes.py", "exec", dont_inherit=True), namespace)
    for task in plan.task_candidates:
        reference = ast.parse(render_node_function(task)).body[0]
        assert isinstance(reference, ast.FunctionDef)
        assert ast.dump(
            ast.Module(body=functions[task.name].body[1:], type_ignores=[])
        ) == ast.dump(ast.Module(body=reference.body, type_ignores=[]))
    second, third, fourth = (namespace[task.name] for task in plan.task_candidates[1:])
    assert typing.get_type_hints(second) == {"value": int, "return": int}
    assert typing.get_type_hints(third) == {"result": int, "return": str}
    assert typing.get_type_hints(fourth) == {"result": str, "return": Any}
    # A deliberately inaccurate string declaration never repairs or certifies integer source.
    assert type(third(4)) is int
    report = json.loads(typed[Path("node-types.json")])
    assert report["declaration"] == contract.to_dict()
    assert report["untyped_datasets"] == ["leaf"]
    assert report["runtime_type_validation"] == "not_run"
    assert report["dataframe_schema_validation"] == "not_supported"
    report_path = tmp_path / "report.json"
    report_path.write_text(typed[Path("node-types.json")], encoding="utf-8")
    with pytest.raises(ProjectGenerationError, match="fields"):
        load_notebook_type_contract(report_path)
    again, _ = render_kedro_project(plan, source_facts=facts)
    assert again == plain


@pytest.mark.parametrize(
    "label",
    [
        "bool",
        "int",
        "float",
        "str",
        "pandas.DataFrame",
        "pandas.Series",
        "numpy.ndarray",
        "sklearn.pipeline.Pipeline",
        "sklearn.base.BaseEstimator",
    ],
)
def test_allowed_annotations_resolve_in_generated_runtime(tmp_path: Path, label: str) -> None:
    pd = importlib.import_module("pandas")
    sklearn_base = importlib.import_module("sklearn.base")
    sklearn_pipeline = importlib.import_module("sklearn.pipeline")
    expected = {
        "bool": bool,
        "int": int,
        "float": float,
        "str": str,
        "pandas.DataFrame": pd.DataFrame,
        "pandas.Series": pd.Series,
        "numpy.ndarray": np.ndarray,
        "sklearn.pipeline.Pipeline": sklearn_pipeline.Pipeline,
        "sklearn.base.BaseEstimator": sklearn_base.BaseEstimator,
    }
    source = _source(tmp_path)
    files, _ = render_kedro_project(
        plan_notebook_path(source),
        source_facts=analyze_notebook_path(source),
        node_types=_contract(source, value=label),
    )
    code, functions = _nodes(files)
    namespace: dict[str, Any] = {}
    exec(compile(code, "nodes.py", "exec", dont_inherit=True), namespace)
    first, second, *_ = functions
    assert typing.get_type_hints(namespace[first])["return"] is expected[label]
    assert typing.get_type_hints(namespace[second])["value"] is expected[label]
    assert label in str(ast.get_docstring(functions[first]))


def test_generation_never_imports_declared_libraries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source(tmp_path)
    facts, plan = analyze_notebook_path(source), plan_notebook_path(source)
    original = builtins.__import__

    def guarded(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.split(".", maxsplit=1)[0] in {"pandas", "numpy", "sklearn"}:
            raise AssertionError("Generation imported a declared ML library")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    files, _ = render_kedro_project(
        plan,
        source_facts=facts,
        node_types=_contract(source, value="sklearn.pipeline.Pipeline", leaf="pandas.DataFrame"),
    )
    assert "import sklearn.pipeline as _ntk_sklearn_pipeline" in _nodes(files)[0]


@pytest.mark.parametrize("problem", ["missing-facts", "wrong-object", "stale", "unknown-dataset"])
def test_invalid_binding_refuses_before_publication(tmp_path: Path, problem: str) -> None:
    source = _source(tmp_path)
    facts, plan = analyze_notebook_path(source), plan_notebook_path(source)
    contract: Any = _contract(source, value="int")
    if problem == "wrong-object":
        contract = "not a contract"
    elif problem == "stale":
        contract = replace(contract, source_sha256="0" * 64)
    elif problem == "unknown-dataset":
        contract = _contract(source, missing="int")
    with pytest.raises(ProjectGenerationError):
        generate_kedro_project(
            plan,
            tmp_path / "blocked",
            source_facts=None if problem == "missing-facts" else facts,
            node_types=contract,
        )
    assert not (tmp_path / "blocked").exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": "2.0"},
        {"source_sha256": None},
        {"source_sha256": "x" * 64},
        {"datasets": []},
        {"datasets": ()},
        {"datasets": ("bad",)},
        {"datasets": (("bad",),)},
        {"datasets": ((1, "int"),)},
        {"datasets": (("a-b", "int"),)},
        {"datasets": (("value", "int"), ("value", "float"))},
        {"datasets": (("value", []),)},
        {"datasets": (("value", "custom.Model"),)},
        {"datasets": (("value", "__import__('os')"),)},
        {"datasets": tuple((f"v{i}", "int") for i in range(MAX_DATASET_TYPES + 1))},
    ],
)
def test_invalid_direct_contracts_are_rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(ProjectGenerationError):
        NotebookTypeContract(
            **{"source_sha256": "a" * 64, "datasets": (("value", "int"),), **changes}
        )


def test_contract_is_immutable_canonical_and_bounded(tmp_path: Path) -> None:
    source = _source(tmp_path)
    contract = _contract(source, z="str", a="int")
    assert contract.datasets == (("a", "int"), ("z", "str"))
    dynamic: Any = contract
    with pytest.raises(FrozenInstanceError):
        dynamic.source_sha256 = "b" * 64
    exported = contract.to_dict()
    exported["datasets"] = {"x": "float"}
    path = tmp_path / "types.json"
    path.write_text(json.dumps(contract.to_dict()), encoding="utf-8")
    assert load_notebook_type_contract(path) == contract
    boundary = NotebookTypeContract(
        "a" * 64, tuple((f"v{i}", "int") for i in range(MAX_DATASET_TYPES))
    )
    assert len(boundary.datasets) == MAX_DATASET_TYPES
    oversized = tuple((f"v{i:03}" + "x" * 252, "int") for i in range(MAX_DATASET_TYPES))
    with pytest.raises(ProjectGenerationError, match=r"Canonical.*64 KiB"):
        NotebookTypeContract("a" * 64, oversized)


@pytest.mark.parametrize(
    "content",
    [
        b"null",
        b"{}",
        b"[]",
        b"invalid",
        b"\xff",
        b'{"schema_version":"1.0","schema_version":"1.0"}',
        b'{"schema_version":"1.0","source_sha256":"a","datasets":{"v":"int","v":"int"}}',
        b'{"schema_version":"1.0","source_sha256":"a","datasets":[]}',
        b"[" * 1100 + b"]" * 1100,
        b" " * (MAX_NODE_TYPE_BYTES + 1),
    ],
    ids=lambda content: repr(content)[:60],
)
def test_bounded_loader_rejects_malformed_input(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "types.json"
    path.write_bytes(content)
    with pytest.raises(ProjectGenerationError):
        load_notebook_type_contract(path)


def test_missing_declaration_file_is_a_typed_error(tmp_path: Path) -> None:
    with pytest.raises(ProjectGenerationError, match="Cannot read node type contract"):
        load_notebook_type_contract(tmp_path / "missing.json")


def test_local_preview_generation_cli_and_root_anchored_settings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _source(tmp_path)
    contract = _contract(source, value="int")
    types = tmp_path / "types.json"
    types.write_text(json.dumps(contract.to_dict()), encoding="utf-8")
    config = LocalProjectConfiguration(tmp_path, source, "notebook", node_types=Path("types.json"))
    location = tmp_path / "project.json"
    location.write_text(json.dumps(config.to_dict()), encoding="utf-8")
    assert load_local_project_configuration(location) == config
    preview = run_local_operation(PlanRequest(config))
    assert isinstance(preview, PlanningResult)
    files = {item.path: item.content for item in preview.files}
    run_local_operation(GenerateRequest(config, Path("published")))
    assert all(
        (tmp_path / "published" / path).read_text(encoding="utf-8") == text
        for path, text in files.items()
    )
    assert main(["generate", str(source), str(tmp_path / "cli"), "--node-types", str(types)]) == 0
    assert (tmp_path / "cli/node-types.json").is_file()
    assert "Created Kedro project" in capsys.readouterr().out
    assert main(["project", "plan", str(location)]) == 0
    assert "node-types.json" in capsys.readouterr().out
    types.write_text(
        json.dumps(replace(contract, source_sha256="0" * 64).to_dict()), encoding="utf-8"
    )
    with pytest.raises(LocalOperationError, match="SHA-256"):
        run_local_operation(GenerateRequest(config, Path("blocked")))
    assert not (tmp_path / "blocked").exists()


def test_type_declarations_are_protected_measurement_inputs_and_not_functional_settings(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    directory = tmp_path / "declarations"
    directory.mkdir()
    types = directory / "types.json"
    types.write_text(json.dumps(_contract(source, value="int").to_dict()), encoding="utf-8")
    config = LocalProjectConfiguration(tmp_path, source, "notebook", node_types=types)
    with pytest.raises(LocalOperationError, match="overlaps"):
        measure_local_operation(InspectRequest(config), directory, case_id="types")
    with pytest.raises(LocalOperationError, match="requires a notebook"):
        replace(config, source_kind="functional")
    with pytest.raises(LocalOperationError, match=r"pathlib\.Path"):
        replace(config, node_types=typing.cast("Any", "types.json"))


def test_profile_names_do_not_change_dataset_declarations(tmp_path: Path) -> None:
    source = _source(tmp_path)
    contract = _contract(source, value="int")
    facts, plan = analyze_notebook_path(source), plan_notebook_path(source)
    plain, _ = render_kedro_project(plan, source_facts=facts, node_types=contract)
    custom, _ = render_kedro_project(
        plan,
        source_facts=facts,
        node_types=contract,
        architecture_profile=KedroArchitectureProfile(
            "typed", "1.0.0", pipeline_name="training", node_name_prefix="ml_"
        ),
    )
    assert custom[Path("node-types.json")] == plain[Path("node-types.json")]


def test_partial_tuple_annotations_and_private_import_collisions(tmp_path: Path) -> None:
    source = _source(tmp_path)
    notebook = json.loads(source.read_text(encoding="utf-8"))
    notebook["cells"][0]["source"] = "_ntk_pandas = 1\nvalue = 3\nlabel = 'ready'"
    source.write_text(json.dumps(notebook), encoding="utf-8")
    contract = _contract(source, value="pandas.DataFrame")
    files, _ = render_kedro_project(
        plan_notebook_path(source), source_facts=analyze_notebook_path(source), node_types=contract
    )
    code, functions = _nodes(files)
    assert "import pandas as _ntk__pandas" in code
    namespace: dict[str, Any] = {}
    exec(compile(code, "nodes.py", "exec", dont_inherit=True), namespace)
    first = next(iter(functions.values()))
    hints = typing.get_type_hints(namespace[first.name])
    actual = typing.get_args(hints["return"])
    assert importlib.import_module("pandas").DataFrame in actual
    assert Any in actual
    assert "pandas.DataFrame" in str(ast.get_docstring(first))


def test_current_source_edit_and_unknown_local_path_are_rejected(tmp_path: Path) -> None:
    source = _source(tmp_path)
    location = tmp_path / "types.json"
    location.write_text(json.dumps(_contract(source, value="int").to_dict()), encoding="utf-8")
    config = LocalProjectConfiguration(tmp_path, source, "notebook", node_types=location)
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(LocalOperationError, match="SHA-256"):
        run_local_operation(PlanRequest(config))
    with pytest.raises(LocalOperationError, match="inside project_root"):
        replace(config, node_types=Path("../outside.json"))
    for value in (None, 17, "../outside.json"):
        data = config.to_dict()
        data["node_types"] = value
        settings = tmp_path / "project.json"
        settings.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(LocalOperationError):
            load_local_project_configuration(settings)


@pytest.mark.parametrize("enforce", [False, True])
def test_type_declarations_do_not_bypass_instruction_accounting(
    tmp_path: Path, *, enforce: bool
) -> None:
    source = _source(tmp_path)
    facts, plan = analyze_notebook_path(source), plan_notebook_path(source)
    changed = replace(plan.task_candidates[0], source="value = 999")
    plan = replace(plan, task_candidates=(changed, *plan.task_candidates[1:]))
    with pytest.raises(ProjectGenerationError, match="SA003"):
        generate_kedro_project(
            plan,
            tmp_path / "blocked",
            source_facts=facts,
            node_types=_contract(source, value="int"),
            enforce_node_types=enforce,
        )
    assert not (tmp_path / "blocked").exists()


def test_credit_example_preview_retains_regression_and_model_evidence() -> None:
    path = (
        Path(__file__).parents[3] / "examples/nested_financial/credit_pipeline/project-typed.json"
    )
    config = load_local_project_configuration(path)
    typed = run_local_operation(PlanRequest(config))
    original = run_local_operation(PlanRequest(replace(config, node_types=None)))
    assert isinstance(typed, PlanningResult)
    assert isinstance(original, PlanningResult)
    files = {item.path: item.content for item in typed.files}
    assert all(
        files[item.path] == item.content
        for item in original.files
        if not item.path.endswith("/nodes.py")
    )
    assert typed.copies == original.copies
    report = json.loads(files["node-types.json"])
    assert len(report["declaration"]["datasets"]) == 28
    assert report["untyped_datasets"] == [
        "categorical_columns",
        "cohort_counts",
        "feature_columns",
        "feature_names",
        "metrics",
        "numeric_columns",
        "summary",
    ]
    assert json.loads(files["model-output.json"])["runtime_type_status"] == "not_verified"

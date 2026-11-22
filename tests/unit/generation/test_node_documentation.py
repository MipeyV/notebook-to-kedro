"""Generated interface metadata preserves executable source and exposes typing gaps."""

import ast
import inspect
import typing
from dataclasses import replace

import pytest

from notebook_to_kedro.generation.kedro import generator
from notebook_to_kedro.generation.kedro.node_documentation import (
    annotation_namespace,
    document_node,
)
from notebook_to_kedro.ir import ConversionPlan, ParameterValue, TaskCandidate
from notebook_to_kedro.ir.plan import PlanParameterValue


def _task() -> TaskCandidate:
    return TaskCandidate(
        id="task-1",
        name="validate",
        inputs=("values",),
        outputs=("result", "count"),
        source_cell_ids=("cell-1",),
        statement_ids=("s1", "s2", "s3"),
        source='assert values, "Empty input"\nresult = values\ncount = len(values)',
    )


def test_metadata_preserves_source_ast_and_runtime_failures() -> None:
    task = _task()
    code = generator._nodes(ConversionPlan("1.0", "test", "test.ipynb", (task,)))
    tree = ast.parse(code)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
    original = ast.parse(generator.render_node_function(task)).body[0]
    assert isinstance(original, ast.FunctionDef)
    assert ast.dump(ast.Module(body=function.body[1:], type_ignores=[])) == ast.dump(
        ast.Module(body=original.body, type_ignores=[])
    )
    doc = ast.get_docstring(function)
    assert doc
    assert all(section in doc for section in ("Args:", "Returns:", "Raises:", "Notes:"))
    assert "Preserved source assertions: 1" in doc
    assert "cell-1" in doc
    namespace: dict[str, typing.Any] = {}
    exec(compile(code, "nodes.py", "exec", dont_inherit=True), namespace)
    validate = namespace[task.name]
    assert typing.get_type_hints(validate) == {
        "values": typing.Any,
        "return": tuple[typing.Any, typing.Any],
    }
    assert validate([1, 2]) == ([1, 2], 2)
    with pytest.raises(AssertionError, match="Empty input"):
        validate([])
    optimized: dict[str, typing.Any] = {}
    exec(compile(code, "nodes.py", "exec", dont_inherit=True, optimize=1), optimized)
    assert optimized[task.name]([]) == ([], 0)  # Preserve the source's -O limitation.
    assert not original.returns
    assert not ast.get_docstring(original)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, bool),
        (1, int),
        (0.2, float),
        ("label", str),
        (None, typing.Any),
        ((1, 2), typing.Any),
        ((("x", 1),), typing.Any),
    ],
)
def test_parameter_default_hints_are_not_guessed_for_containers(
    value: PlanParameterValue, expected: object
) -> None:
    task = replace(_task(), parameters=("validate.setting",))
    parameter = ParameterValue("validate.setting", value, "validate_setting", "cell-1")
    # Documentation consumes the already rendered wrapper, without changing parameter evidence.
    raw = "def validate(values, validate_setting):\n    return values\n"
    code = document_node(raw, task, {parameter.name: parameter}, "_ntk")
    namespace: dict[str, typing.Any] = {
        "_ntk_typing": typing,
        "_ntk_builtins": __import__("builtins"),
    }
    exec(compile(code, "nodes.py", "exec", dont_inherit=True), namespace)
    assert typing.get_type_hints(namespace[task.name])["validate_setting"] is expected
    assert "annotation based on its default" in namespace[task.name].__doc__


@pytest.mark.parametrize("outputs", [(), ("result",)])
def test_zero_and_single_output_with_no_arguments(outputs: tuple[str, ...]) -> None:
    task = replace(_task(), inputs=(), outputs=outputs, source="result = 1", source_cell_ids=())
    code = generator._nodes(ConversionPlan("1.0", "test", "test.ipynb", (task,)))
    namespace: dict[str, typing.Any] = {}
    exec(compile(code, "nodes.py", "exec", dont_inherit=True), namespace)
    function = namespace[task.name]
    assert typing.get_type_hints(function)["return"] is (typing.Any if outputs else type(None))
    assert "Args:" not in function.__doc__
    assert "Raises:" not in function.__doc__
    assert "notebook cells unavailable" in function.__doc__
    assert function() == (1 if outputs else None)


def test_private_annotation_imports_avoid_source_and_profile_names() -> None:
    task = replace(_task(), source="_ntk_typing = 3\nresult = values\ncount = len(values)")
    plan = ConversionPlan(
        "1.0", "test", "test.ipynb", (task,), imports=("import math as _ntk__builtins",)
    )
    code = generator._nodes(plan, {task.id: "_ntk___typing"})
    assert "import typing as _ntk____typing" in code
    namespace: dict[str, typing.Any] = {}
    exec(compile(code, "nodes.py", "exec", dont_inherit=True), namespace)
    assert typing.get_type_hints(namespace["_ntk___typing"])["values"] is typing.Any
    assert annotation_namespace("unrelated") == "_ntk"


def test_untrusted_provenance_is_a_literal_and_nested_asserts_are_counted() -> None:
    task = replace(
        _task(),
        id='bad"""\nraise RuntimeError("injected")',
        source="if values:\n    assert values[0]\nresult = values\ncount = len(values)",
    )
    code = generator._nodes(ConversionPlan("1.0", "test", "test.ipynb", (task,)))
    namespace: dict[str, typing.Any] = {}
    exec(compile(code, "nodes.py", "exec", dont_inherit=True), namespace)
    assert task.id in str(inspect.getdoc(namespace[task.name]))
    assert "Preserved source assertions: 1" in namespace[task.name].__doc__


def test_documentation_rejects_nonfunction_input() -> None:
    with pytest.raises(ValueError, match="requires a function"):
        document_node("result = 1", _task(), {}, "_ntk")


def test_future_imports_and_builtin_shadowing_keep_annotations_resolvable() -> None:
    task = replace(_task(), source="tuple = 1\nresult = values\ncount = len(values)")
    plan = ConversionPlan(
        "1.0", "test", "test.ipynb", (task,), imports=("from __future__ import annotations",)
    )
    code = generator._nodes(plan)
    namespace: dict[str, typing.Any] = {}
    exec(compile(code, "nodes.py", "exec", dont_inherit=True), namespace)
    assert typing.get_type_hints(namespace[task.name])["return"] == tuple[typing.Any, typing.Any]

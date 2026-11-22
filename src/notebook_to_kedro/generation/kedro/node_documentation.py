"""Document generated interfaces without changing source bodies or provider contracts."""

from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from notebook_to_kedro.ir import ParameterValue, TaskCandidate


def annotation_namespace(source: str) -> str:
    """Choose private annotation imports absent from all generated source identifiers."""
    names = set(re.findall(r"\w+", source))
    prefix = "_ntk"
    while {f"{prefix}_typing", f"{prefix}_builtins"} & names:
        prefix += "_"
    return prefix


def document_node(
    code: str,
    task: TaskCandidate,
    parameters: Mapping[str, ParameterValue],
    namespace: str,
) -> str:
    """Add Google-style documentation and explicitly provisional interface annotations."""
    tree = ast.parse(code)
    function = tree.body[0]
    if not isinstance(function, ast.FunctionDef):
        raise ValueError("Node documentation requires a function")
    unknown = f"{namespace}_typing.Any"
    hints = dict.fromkeys(task.inputs, unknown)
    descriptions = dict.fromkeys(task.inputs, "Source input; runtime type requires review.")
    for name in task.parameters:
        parameter = parameters[name]
        argument = name.replace(".", "_")
        # A configuration default supplies a review hint, never a runtime type guarantee.
        scalar = type(parameter.value).__name__
        hints[argument] = (
            f"{namespace}_builtins.{scalar}"
            if scalar in {"bool", "int", "float", "str"}
            else unknown
        )
        descriptions[argument] = f"Kedro parameter {name}; annotation based on its default."

    result = unknown
    if not task.outputs:
        result = "None"
    elif len(task.outputs) > 1:
        result = f"{namespace}_builtins.tuple[{', '.join([unknown] * len(task.outputs))}]"
    arguments = ", ".join(f"{name}: {hint!r}" for name, hint in hints.items())
    lines = [f"Run source task {task.id}.", ""]
    if hints:
        lines.extend(["Args:", *(f"    {name}: {descriptions[name]}" for name in hints), ""])
    display_result = result.replace(f"{namespace}_typing.", "").replace(
        f"{namespace}_builtins.", ""
    )
    lines.extend(
        [
            "Returns:",
            f"    {display_result}: Source outputs in order: {', '.join(task.outputs) or 'None'}.",
            "",
        ]
    )
    assertions = sum(isinstance(node, ast.Assert) for node in ast.walk(function))
    if assertions:
        lines.extend(
            [
                "Raises:",
                "    AssertionError: A preserved source assertion fails.",
                "",
            ]
        )
    lines.extend(
        [
            "Notes:",
            f"    Source cells: {', '.join(task.source_cell_ids) or 'notebook cells unavailable'}.",
            "    Any marks an unresolved runtime type, not a validated interface.",
            "    Parameter hints describe defaults; review configuration overrides.",
            f"    Preserved source assertions: {assertions}. Python -O disables assertions.",
            "    Other source/library exceptions propagate unchanged.",
        ]
    )
    # Unparse only the documentation literal, leaving every source instruction untouched.
    literal = ast.unparse(
        ast.Module(
            body=[ast.Expr(value=ast.Constant(value="\n".join(lines) + "\n"))], type_ignores=[]
        )
    )
    documentation = "\n".join("    " + line if line else "" for line in literal.splitlines())
    _, _, body = code.partition("\n")
    return f"def {function.name}({arguments}) -> {result!r}:\n{documentation}\n{body}"

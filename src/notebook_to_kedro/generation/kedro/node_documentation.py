"""Document generated interfaces without changing source bodies or provider contracts."""

from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from notebook_to_kedro.ir import ParameterValue, TaskCandidate


def annotation_namespace(source: str, modules: tuple[str, ...] = ()) -> str:
    """Choose private annotation imports absent from all generated source identifiers."""
    names = set(re.findall(r"\w+", source))
    prefix = "_ntk"
    while {f"{prefix}_{module}" for module in ("typing", "builtins", *modules)} & names:
        prefix += "_"
    return prefix


def document_node(  # noqa: PLR0913
    code: str,
    task: TaskCandidate,
    parameters: Mapping[str, ParameterValue],
    namespace: str,
    *,
    input_types: Mapping[str, str | None] | None = None,
    output_types: tuple[str | None, ...] | None = None,
    runtime_checks: bool = False,
) -> str:
    """Add Google-style documentation and explicitly provisional interface annotations."""
    tree = ast.parse(code)
    function = tree.body[0]
    if not isinstance(function, ast.FunctionDef):
        raise ValueError("Node documentation requires a function")
    unknown = f"{namespace}_typing.Any"
    hints = dict.fromkeys(task.inputs, unknown)
    descriptions = dict.fromkeys(task.inputs, "Source input; runtime type requires review.")
    for name, annotation in ({} if input_types is None else input_types).items():
        if annotation is not None:
            hints[name] = annotation
            descriptions[name] = (
                "Explicitly declared dataset type; checked at this call boundary."
                if runtime_checks
                else "Explicitly declared dataset type; runtime validation not run."
            )
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

    outputs = tuple(
        unknown if annotation is None else annotation
        for annotation in ((None,) * len(task.outputs) if output_types is None else output_types)
    )
    result = unknown if not outputs else outputs[0]
    if not task.outputs:
        result = "None"
    elif len(task.outputs) > 1:
        result = f"{namespace}_builtins.tuple[{', '.join(outputs)}]"
    arguments = ", ".join(f"{name}: {hint!r}" for name, hint in hints.items())
    lines = [f"Run source task {task.id}.", ""]
    if hints:
        lines.extend(["Args:", *(f"    {name}: {descriptions[name]}" for name in hints), ""])
    display_result = result.replace(f"{namespace}_typing.", "").replace(
        f"{namespace}_builtins.", ""
    )
    for module, display in (
        ("pandas", "pandas"),
        ("numpy", "numpy"),
        ("sklearn_pipeline", "sklearn.pipeline"),
        ("sklearn_base", "sklearn.base"),
    ):
        display_result = display_result.replace(f"{namespace}_{module}.", f"{display}.")
    lines.extend(
        [
            "Returns:",
            f"    {display_result}: Source outputs in order: {', '.join(task.outputs) or 'None'}.",
            "",
        ]
    )
    assertions = sum(isinstance(node, ast.Assert) for node in ast.walk(function))
    raises: list[str] = []
    if assertions:
        raises.append("    AssertionError: A preserved source assertion fails.")
    if runtime_checks:
        raises.append(
            "    TypeError: A declared input/output class or return tuple is incompatible."
        )
    if raises:
        lines.extend(["Raises:", *raises, ""])
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
    if input_types is not None:
        lines.append(
            "    Declared classes are checked on calls; values/schemas/fitted state are not."
            if runtime_checks
            else "    Explicit dataset types are declarations, not verified runtime contracts."
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

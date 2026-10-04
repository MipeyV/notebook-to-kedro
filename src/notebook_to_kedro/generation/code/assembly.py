"""Assemble untrusted node bodies into validated functions without execution."""

from __future__ import annotations

import ast
import symtable
from typing import TYPE_CHECKING

from notebook_to_kedro.generation.code.contracts import NODE_CODE_SCHEMA_VERSION, NodeCodeResponse
from notebook_to_kedro.generation.code.validation import _import_tree, validate_node_code

if TYPE_CHECKING:
    from notebook_to_kedro.generation.code.contracts import NodeBodyResponse, NodeCodeRequest

NODE_BODY_ASSEMBLY_VERSION = "node-body-assembly-v1"


def _function_code(request: NodeCodeRequest, body_code: str) -> str:
    body = ast.parse(body_code).body
    if not body:
        raise ValueError("body_code must contain statements")
    module = ast.parse(f"def {request.node_name}({', '.join(request.arguments)}):\n    pass")
    function = module.body[0]
    assert isinstance(function, ast.FunctionDef)
    output = ", ".join(request.outputs) if request.outputs else "None"
    function.body = [*body, *ast.parse(f"return {output}").body]
    return ast.unparse(ast.fix_missing_locations(module)) + "\n"


def _global_references(table: symtable.SymbolTable) -> set[str]:
    names = {
        symbol.get_name()
        for symbol in table.get_symbols()
        if symbol.is_referenced() and symbol.is_global()
    }
    for child in table.get_children():
        names.update(_global_references(child))
    return names


def _needed_imports(request: NodeCodeRequest, function_code: str) -> tuple[str, ...]:
    references = _global_references(symtable.symtable(function_code, "<node-body>", "exec"))
    selected = []
    for source in request.allowed_imports:
        statement = _import_tree(source)
        bindings = {
            alias.asname
            or (alias.name.split(".")[0] if isinstance(statement, ast.Import) else alias.name)
            for alias in statement.names
        }
        if bindings & references:
            selected.append(source)
    return tuple(selected)


def assemble_node_body(request: NodeCodeRequest, response: NodeBodyResponse) -> NodeCodeResponse:
    """Add the trusted interface and return, then enforce unchanged static validation.

    Imports come only from request permissions. Body statements are not repaired or
    parameterized here. AST normalization can change formatting, but not values.
    No proposed code or imported module is executed.
    """
    if response.request_id != request.request_id or response.task_id != request.task_id:
        raise ValueError("response identity does not match the requested node")
    try:
        function_code = _function_code(request, response.body_code)
        imports = _needed_imports(request, function_code)
    except (SyntaxError, ValueError) as error:
        raise ValueError(f"Invalid node body: {error}") from error
    assembled = NodeCodeResponse(
        schema_version=NODE_CODE_SCHEMA_VERSION,
        request_id=response.request_id,
        task_id=response.task_id,
        function_code=function_code,
        imports=imports,
        review_notes=response.review_notes,
    )
    validate_node_code(request, assembled)
    return assembled

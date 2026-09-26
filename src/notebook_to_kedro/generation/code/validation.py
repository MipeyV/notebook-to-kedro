"""Conservative static validation, not a sandbox or an equivalence proof."""

from __future__ import annotations

import ast
import builtins
import symtable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from notebook_to_kedro.generation.code.contracts import NodeCodeRequest, NodeCodeResponse

NODE_CODE_VALIDATOR_VERSION = "node-code-validation-v2"


def _import_tree(source: str) -> ast.Import | ast.ImportFrom:
    body = ast.parse(source).body
    if len(body) != 1 or not isinstance(body[0], (ast.Import, ast.ImportFrom)):
        raise ValueError("each import must contain exactly one import statement")
    node = body[0]
    if isinstance(node, ast.ImportFrom) and (node.level or any(a.name == "*" for a in node.names)):
        raise ValueError("relative and wildcard imports are unsupported")
    return node


def _validate_imports(request: NodeCodeRequest, response: NodeCodeResponse) -> set[str]:
    allowed = {ast.dump(_import_tree(source)) for source in request.allowed_imports}
    bindings: set[str] = set()
    for source in response.imports:
        node = _import_tree(source)
        if ast.dump(node) not in allowed:
            raise ValueError("response contains an unauthorized import")
        for alias in node.names:
            name = alias.asname or (
                alias.name.split(".")[0] if isinstance(node, ast.Import) else alias.name
            )
            if name in bindings or name == request.node_name:
                raise ValueError("import binding collision")
            bindings.add(name)
    return bindings


def _function(request: NodeCodeRequest, code: str) -> ast.FunctionDef:
    body = ast.parse(code).body
    if len(body) != 1 or not isinstance(body[0], ast.FunctionDef):
        raise ValueError("function_code must contain exactly one synchronous function")
    function = body[0]
    args = function.args
    if function.name != request.node_name:
        raise ValueError("function name does not match the requested node")
    if (
        tuple(arg.arg for arg in args.args) != request.arguments
        or args.posonlyargs
        or args.kwonlyargs
        or args.vararg
        or args.kwarg
        or args.defaults
    ):
        raise ValueError("function signature does not match the requested arguments")
    if (
        function.decorator_list
        or function.returns is not None
        or any(arg.annotation is not None for arg in args.args)
        or getattr(function, "type_params", False)
    ):
        raise ValueError("decorators, annotations and type parameters are unsupported")
    forbidden = (
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Lambda,
        ast.Global,
        ast.Nonlocal,
        ast.Yield,
        ast.YieldFrom,
        ast.Import,
        ast.ImportFrom,
    )
    for node in ast.walk(function):
        if isinstance(node, forbidden) or (
            isinstance(node, ast.FunctionDef) and node is not function
        ):
            raise ValueError("unsupported nested scope, import or scope-changing statement")
    return function


def _validate_return(function: ast.FunctionDef, outputs: tuple[str, ...]) -> None:
    last = function.body[-1]
    returns = [node for node in ast.walk(function) if isinstance(node, ast.Return)]
    if not isinstance(last, ast.Return) or len(returns) != 1:
        raise ValueError("exactly one terminal return is required")
    expected: ast.expr
    if not outputs:
        expected = ast.Constant(value=None)
    elif len(outputs) == 1:
        expected = ast.Name(id=outputs[0], ctx=ast.Load())
    else:
        expected = ast.Tuple(
            elts=[ast.Name(id=name, ctx=ast.Load()) for name in outputs], ctx=ast.Load()
        )
    if ast.dump(last.value or ast.Constant(value=None)) != ast.dump(expected):
        raise ValueError("return must match the ordered output names")


def _assertion_blocks(statements: list[ast.stmt]) -> list[tuple[int, str]]:
    # Preserve whole enclosing statements so moving an assert under a false guard cannot pass.
    return [
        (index, ast.dump(statement))
        for index, statement in enumerate(statements)
        if any(isinstance(node, ast.Assert) for node in ast.walk(statement))
    ]


def _validate_assertions(request: NodeCodeRequest, function: ast.FunctionDef) -> None:
    original = _assertion_blocks(ast.parse(request.raw_source).body)
    if original != _assertion_blocks(function.body):
        raise ValueError(
            "assertions and their enclosing statements must retain source AST and position"
        )


def _validate_globals(table: symtable.SymbolTable, allowed: set[str]) -> None:
    unknown = sorted(
        symbol.get_name()
        for symbol in table.get_symbols()
        if symbol.is_referenced() and symbol.is_global() and symbol.get_name() not in allowed
    )
    if unknown:
        raise ValueError(f"unknown global names: {', '.join(unknown)}")
    for child in table.get_children():
        _validate_globals(child, allowed)


def validate_node_code(request: NodeCodeRequest, response: NodeCodeResponse) -> None:
    """Check identity, imports, signature, assertions, names, returns and compilation."""
    if (response.request_id, response.task_id) != (request.request_id, request.task_id):
        raise ValueError("response identity does not match the requested node")
    try:
        bindings = _validate_imports(request, response)
        function = _function(request, response.function_code)
        _validate_return(function, request.outputs)
        _validate_assertions(request, function)
        source = "\n".join((*response.imports, response.function_code))
        compile(source, "<node-code>", "exec", dont_inherit=True)
        table = symtable.symtable(source, "<node-code>", "exec")
        _validate_globals(table, bindings | set(vars(builtins)))
    except (SyntaxError, ValueError) as error:
        raise ValueError(f"Invalid node code: {error}") from error

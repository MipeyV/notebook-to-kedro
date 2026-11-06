"""Small Python AST primitives shared by notebook and structured-function analysis."""

import ast
import builtins

BUILTIN_NAMES = frozenset(dir(builtins))
DYNAMIC_CALLS = frozenset({"exec", "eval", "compile", "globals", "locals"})
MUTATING_METHODS = frozenset({"fit", "fit_transform", "partial_fit"})


def qualified_name(node: ast.expr) -> str:
    """Describe syntactic call names without resolving imports or object identities."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{qualified_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return qualified_name(node.func)
    return type(node).__name__

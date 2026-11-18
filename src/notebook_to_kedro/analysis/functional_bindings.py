"""Conservative definite local bindings for preserved structured function bodies."""

from __future__ import annotations

import ast


def _stores(node: ast.AST) -> set[str]:
    return {
        item.id
        for item in ast.walk(node)
        if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store)
    }


def _merge(left: set[str] | None, right: set[str] | None) -> set[str] | None:
    if left is None:
        return right
    return left if right is None else left & right


def unbound_local_reads(
    statements: list[ast.stmt], parameters: set[str], locals_: set[str]
) -> tuple[ast.stmt, ...]:
    """Report reads missing on some normal path, without executing or proving loop behavior.

    Branches that raise/return/break/continue have no normal fallthrough. Loop targets/body/else
    bindings are never assumed available afterwards: iteration counts and break paths are unknown.
    Unsupported syntax is still rejected separately by the functional body checker.
    """
    issues: list[ast.stmt] = []

    def read(node: ast.AST, available: set[str], owner: ast.stmt) -> None:
        names = {
            item.id
            for item in ast.walk(node)
            if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load)
        }
        if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        if (names & locals_) - available:
            issues.append(owner)

    def block(body: list[ast.stmt], initial: set[str]) -> set[str] | None:
        available: set[str] | None = set(initial)
        for statement in body:
            if available is None:
                break
            if isinstance(statement, ast.If):
                read(statement.test, available, statement)
                available = _merge(
                    block(statement.body, available), block(statement.orelse, available)
                )
            elif isinstance(statement, (ast.For, ast.While)):
                if isinstance(statement, ast.For):
                    read(statement.iter, available, statement)
                    read(statement.target, available, statement)
                    loop_bound = available | _stores(statement.target)
                else:
                    read(statement.test, available, statement)
                    loop_bound = available
                block(statement.body, loop_bound)
                block(statement.orelse, available)
            else:
                read(statement, available, statement)
                if not isinstance(statement, ast.AnnAssign) or statement.value is not None:
                    available.update(_stores(statement))
                if isinstance(statement, (ast.Raise, ast.Return, ast.Break, ast.Continue)):
                    available = None
        return available

    block(statements, parameters)
    return tuple(issues)

"""Read-only analysis of explicit, straight-line Python functions across source units."""

from __future__ import annotations

import ast
import copy
import hashlib
import symtable
from collections import Counter
from graphlib import CycleError, TopologicalSorter
from typing import TYPE_CHECKING, Literal

from notebook_to_kedro.analysis.python_ast import (
    BUILTIN_NAMES,
    DYNAMIC_CALLS,
    MUTATING_METHODS,
    qualified_name,
)
from notebook_to_kedro.ir.functional import (
    BlockDependency,
    BlockDiagnostic,
    BlockSpan,
    BlockStatement,
    FunctionalAnalysis,
    FunctionalBlock,
)

if TYPE_CHECKING:
    from notebook_to_kedro.ir.functional import SourceUnit


def _span(unit: SourceUnit, node: ast.stmt) -> BlockSpan:
    start = node.lineno
    if isinstance(node, ast.FunctionDef) and node.decorator_list:
        start = min(item.lineno for item in node.decorator_list)
        # Parenthesized decorators can begin before the expression's AST location.
        lines = unit.source.splitlines()
        start = next(
            index + 1 for index in range(start - 1, -1, -1) if lines[index].startswith("@")
        )
    return BlockSpan(
        unit.id, start, node.end_lineno or node.lineno, node.col_offset, node.end_col_offset or 0
    )


def _source(unit: SourceUnit, node: ast.stmt) -> str:
    source = ast.get_source_segment(unit.source, node) or ""
    if isinstance(node, ast.FunctionDef) and node.decorator_list:
        lines = unit.source.splitlines(keepends=True)
        source = "".join(lines[_span(unit, node).start_line - 1 : node.lineno - 1]) + source
    return source


def _ast_sha256(node: ast.AST) -> str:
    return hashlib.sha256(ast.dump(node).encode("utf-8")).hexdigest()


def _issue(
    code: str, message: str, unit: SourceUnit, node: ast.stmt, block_id: str | None = None
) -> BlockDiagnostic:
    return BlockDiagnostic(code, "error", message, _span(unit, node), block_id)


def _signature_supported(node: ast.FunctionDef) -> bool:
    return not (
        node.decorator_list
        or node.args.posonlyargs
        or node.args.kwonlyargs
        or node.args.defaults
        or node.args.vararg
        or node.args.kwarg
        or bool(getattr(node, "type_params", ()))
        or any(
            isinstance(item, ast.Call)
            for arg in (*node.args.args,)
            if arg.annotation is not None
            for item in ast.walk(arg.annotation)
        )
        or (
            node.returns is not None
            and any(isinstance(item, ast.Call) for item in ast.walk(node.returns))
        )
    )


def _outputs(node: ast.FunctionDef) -> tuple[str, ...] | None:
    returns = [item for item in ast.walk(node) if isinstance(item, ast.Return)]
    if len(returns) != 1 or node.body[-1] is not returns[0]:
        return None
    value = returns[0].value
    if isinstance(value, ast.Name):
        return (value.id,)
    if (
        isinstance(value, ast.Tuple)
        and value.elts
        and all(isinstance(item, ast.Name) for item in value.elts)
    ):
        return tuple(item.id for item in value.elts if isinstance(item, ast.Name))
    return None


def _body_checks(
    unit: SourceUnit, node: ast.FunctionDef, block_id: str, table: symtable.SymbolTable
) -> tuple[BlockDiagnostic, ...]:
    diagnostics: list[BlockDiagnostic] = []
    allowed = (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Assert, ast.Expr, ast.Return)
    forbidden = (
        ast.Lambda,
        ast.ListComp,
        ast.SetComp,
        ast.DictComp,
        ast.GeneratorExp,
        ast.NamedExpr,
        ast.Yield,
        ast.YieldFrom,
        ast.Await,
    )
    if any(not isinstance(item, allowed) for item in node.body) or any(
        isinstance(item, forbidden) for statement in node.body for item in ast.walk(statement)
    ):
        diagnostics.append(
            _issue(
                "BL004",
                "Only straight-line assignment/assertion/call/return bodies are supported.",
                unit,
                node,
                block_id,
            )
        )
    locals_ = {symbol.get_name() for symbol in table.get_symbols() if symbol.is_local()}
    available = {
        arg.arg for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
    }
    for statement in node.body:
        reads = {
            item.id
            for item in ast.walk(statement)
            if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load)
        }
        if isinstance(statement, ast.AugAssign) and isinstance(statement.target, ast.Name):
            reads.add(statement.target.id)
        if (reads & locals_) - available:
            diagnostics.append(
                _issue(
                    "BL006",
                    "A local name is read before its straight-line binding.",
                    unit,
                    statement,
                    block_id,
                )
            )
        targets = [
            item
            for item in ast.walk(statement)
            if isinstance(item, (ast.Attribute, ast.Subscript)) and isinstance(item.ctx, ast.Store)
        ]
        if targets:
            diagnostics.append(
                _issue(
                    "BL004",
                    "Attribute/subscript writes require an explicit mutation model.",
                    unit,
                    statement,
                    block_id,
                )
            )
        calls = [item for item in ast.walk(statement) if isinstance(item, ast.Call)]
        for call in calls:
            name = qualified_name(call.func)
            if name.rsplit(".", maxsplit=1)[-1] in DYNAMIC_CALLS:
                diagnostics.append(
                    _issue(
                        "BL004",
                        "Dynamic execution/namespace calls are unsupported.",
                        unit,
                        statement,
                        block_id,
                    )
                )
            if not isinstance(call.func, (ast.Name, ast.Attribute)) or (
                isinstance(call.func, ast.Name) and call.func.id in locals_
            ):
                diagnostics.append(
                    _issue(
                        "BL008",
                        "Indirect/local callable targets cannot be resolved in this slice.",
                        unit,
                        statement,
                        block_id,
                    )
                )
        if not isinstance(statement, ast.AnnAssign) or statement.value is not None:
            available.update(
                item.id
                for item in ast.walk(statement)
                if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store)
            )
    return tuple(diagnostics)


def _function(
    unit: SourceUnit, node: ast.FunctionDef, block_id: str
) -> tuple[FunctionalBlock, tuple[BlockDiagnostic, ...]]:
    diagnostics: list[BlockDiagnostic] = []
    source = _source(unit, node)
    if not _signature_supported(node):
        diagnostics.append(
            _issue(
                "BL003",
                "Decorators, defaults, special signatures and annotation calls are unsupported.",
                unit,
                node,
                block_id,
            )
        )
    outputs = _outputs(node)
    if outputs is None:
        diagnostics.append(
            _issue(
                "BL003",
                "Exactly one terminal return of named values is required.",
                unit,
                node,
                block_id,
            )
        )
    inspected = copy.deepcopy(node)
    inspected.decorator_list = []
    inspected.returns = None
    inspected.args.defaults = []
    inspected.args.kw_defaults = [None] * len(inspected.args.kwonlyargs)
    inspected.type_params = []
    for argument in ast.walk(inspected.args):
        if isinstance(argument, ast.arg):
            argument.annotation = None
    module = symtable.symtable(ast.unparse(inspected), unit.path, "exec")
    table = next(item for item in module.get_children() if item.get_name() == node.name)
    globals_ = tuple(
        sorted(
            symbol.get_name()
            for symbol in table.get_symbols()
            if symbol.is_referenced() and symbol.is_global()
        )
    )
    calls = tuple(
        dict.fromkeys(
            qualified_name(item.func)
            for statement in node.body
            for item in ast.walk(statement)
            if isinstance(item, ast.Call)
        )
    )
    mutations = tuple(
        dict.fromkeys(
            qualified_name(item.func.value)
            for statement in node.body
            for item in ast.walk(statement)
            if isinstance(item, ast.Call)
            and isinstance(item.func, ast.Attribute)
            and item.func.attr in MUTATING_METHODS
        )
    )
    parameters = tuple(
        arg.arg for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
    )
    block = FunctionalBlock(
        block_id,
        node.name,
        parameters,
        outputs or (),
        source,
        _ast_sha256(node),
        _span(unit, node),
        globals_,
        calls,
        mutations,
    )
    diagnostics.extend(_body_checks(unit, node, block_id, table))
    if calls:
        diagnostics.append(
            BlockDiagnostic(
                "BL101",
                "warning",
                "Call effects/object identities have not been verified at runtime.",
                block.span,
                block.id,
            )
        )
    if mutations:
        diagnostics.append(
            BlockDiagnostic(
                "BL102",
                "warning",
                "Known call patterns may mutate receiver objects.",
                block.span,
                block.id,
            )
        )
    if node.returns is not None or any(arg.annotation is not None for arg in node.args.args):
        diagnostics.append(
            BlockDiagnostic(
                "BL103",
                "warning",
                "Annotation source is retained; types and definition-time behavior are unverified.",
                block.span,
                block.id,
            )
        )
    return block, tuple(diagnostics)


def _dependencies(
    blocks: tuple[FunctionalBlock, ...], bindings: set[str]
) -> tuple[tuple[BlockDependency, ...], tuple[BlockDiagnostic, ...]]:
    counts = Counter(block.name for block in blocks)
    known = {block.name: block.id for block in blocks if counts[block.name] == 1}
    edges: list[BlockDependency] = []
    diagnostics: list[BlockDiagnostic] = []
    for block in blocks:
        if counts[block.name] != 1 or block.name in bindings:
            diagnostics.append(
                BlockDiagnostic(
                    "BL002",
                    "error",
                    "Function name has ambiguous/redefined module bindings.",
                    block.span,
                    block.id,
                )
            )
        unknown = set(block.global_reads) - bindings - known.keys() - BUILTIN_NAMES
        if unknown:
            diagnostics.append(
                BlockDiagnostic(
                    "BL005",
                    "error",
                    f"Unresolved function globals: {', '.join(sorted(unknown))}.",
                    block.span,
                    block.id,
                )
            )
        edges.extend(
            BlockDependency(block.id, known[name], "call" if name in block.calls else "reference")
            for name in block.global_reads
            if name in known
        )
    graph = {
        block.id: {edge.callee_id for edge in edges if edge.caller_id == block.id}
        for block in blocks
    }
    try:
        tuple(TopologicalSorter(graph).static_order())
    except CycleError:
        diagnostics.append(
            BlockDiagnostic("BL007", "error", "Cyclic function dependencies are unsupported.")
        )
    return tuple(edges), tuple(diagnostics)


def analyze_functional_blocks(sources: tuple[SourceUnit, ...]) -> FunctionalAnalysis:
    """Inspect source units without execution, imports, provider calls or filesystem I/O."""
    if len({unit.id for unit in sources}) != len(sources):
        raise ValueError("Source unit IDs must be unique")
    blocks: list[FunctionalBlock] = []
    statements: list[BlockStatement] = []
    diagnostics: list[BlockDiagnostic] = []
    bindings: set[str] = set()
    for unit in sources:
        try:
            module = ast.parse(unit.source, filename=unit.path)
            compile(unit.source, unit.path, "exec", dont_inherit=True)
        except SyntaxError as error:
            diagnostics.append(
                BlockDiagnostic("BL001", "error", f"Invalid Python in {unit.id}: {error.msg}.")
            )
            continue
        for index, node in enumerate(module.body):
            block_id = None
            kind: Literal["import", "function", "documentation", "unsupported"]
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                kind = "import"
                if isinstance(node, ast.ImportFrom) and (
                    node.level or any(alias.name == "*" for alias in node.names)
                ):
                    diagnostics.append(
                        _issue(
                            "BL002",
                            "Relative/wildcard import bindings are unsupported.",
                            unit,
                            node,
                        )
                    )
                imported_names = [
                    alias.asname
                    or (alias.name.split(".")[0] if isinstance(node, ast.Import) else alias.name)
                    for alias in node.names
                ]
                imported = set(imported_names)
                if imported & bindings or len(imported) != len(imported_names):
                    diagnostics.append(
                        _issue("BL002", "Repeated import bindings are ambiguous.", unit, node)
                    )
                bindings.update(imported)
            elif (
                index == 0
                and isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                kind = "documentation"
            elif isinstance(node, ast.FunctionDef):
                kind = "function"
                block_id = f"block-{len(blocks):04d}"
                block, issues = _function(unit, node, block_id)
                blocks.append(block)
                diagnostics.extend(issues)
            else:
                kind = "unsupported"
                diagnostics.append(
                    _issue(
                        "BL002",
                        "Module-level executable statements require a separate workflow contract.",
                        unit,
                        node,
                    )
                )
            statements.append(
                BlockStatement(
                    f"{unit.id}:stmt-{index:04d}",
                    kind,
                    _source(unit, node),
                    _ast_sha256(node),
                    _span(unit, node),
                    block_id,
                )
            )
    edges, issues = _dependencies(tuple(blocks), bindings)
    diagnostics.extend(issues)
    if not blocks:
        diagnostics.append(
            BlockDiagnostic("BL009", "error", "No explicit synchronous function blocks were found.")
        )
    return FunctionalAnalysis(sources, tuple(statements), tuple(blocks), edges, tuple(diagnostics))

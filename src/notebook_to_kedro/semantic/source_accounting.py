"""Read-only accounting of source statements against a proposed conversion."""

from __future__ import annotations

import ast
import hashlib
import json
import posixpath
from collections import Counter
from dataclasses import asdict, dataclass, replace
from itertools import takewhile
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Literal

from notebook_to_kedro.exceptions import ConversionPlanValidationError
from notebook_to_kedro.ir import PlanDiagnostic
from notebook_to_kedro.semantic.planner import plan_tasks
from notebook_to_kedro.semantic.validation import validate_conversion_plan

if TYPE_CHECKING:
    from notebook_to_kedro.ir import ConversionPlan, NotebookFacts, StatementFacts

SOURCE_ACCOUNTING_VERSION = "1.0"
StatementKind = Literal["task", "module_import", "catalog", "unhandled"]


@dataclass(frozen=True, slots=True)
class StatementDisposition:
    """One original top-level statement and its explicit destination or failure."""

    statement_id: str
    source_cell_id: str
    disposition: StatementKind
    destinations: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class ConversionSourceAudit:
    """Recomputed static evidence; never an authorization or equivalence proof."""

    notebook_path: str
    notebook_sha256: str
    plan_sha256: str
    statements: tuple[StatementDisposition, ...]
    diagnostics: tuple[PlanDiagnostic, ...]
    schema_version: str = SOURCE_ACCOUNTING_VERSION

    @property
    def complete(self) -> bool:
        """Indicate complete accounting and the limited static checks of this version."""
        return not self.diagnostics

    def to_json(self) -> str:
        """Serialize deterministic evidence; consumers must recompute it to validate a plan."""
        return (
            json.dumps({**asdict(self), "complete": self.complete}, sort_keys=True, indent=2) + "\n"
        )


def _plan_sha256(plan: ConversionPlan) -> str:
    payload = json.dumps(asdict(plan), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _issue(code: str, message: str, task_id: str | None = None) -> PlanDiagnostic:
    return PlanDiagnostic(code, "error", message, task_id)


def _tree(source: str) -> str:
    return ast.dump(ast.parse(source))


def _pandas_aliases(facts: NotebookFacts, statement_id: str) -> set[str]:
    aliases: set[str] = set()
    statements = (statement for cell in facts.cells for statement in cell.statements)
    for statement in takewhile(lambda item: item.id != statement_id, statements):
        aliases.difference_update(statement.writes)
        if statement.ast_type == "Import":
            imported = ast.parse(statement.source).body[0]
            if isinstance(imported, ast.Import):
                aliases.update(
                    alias.asname or "pandas" for alias in imported.names if alias.name == "pandas"
                )
    return aliases


def _catalog_claim(
    facts: NotebookFacts, statement: StatementFacts, plan: ConversionPlan
) -> int | None:
    """Recognize only the exact pandas CSV relocation currently rendered by Kedro."""
    node = ast.parse(statement.source).body[0]
    if not (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Call)
    ):
        return None
    call = node.value
    if not (
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id in _pandas_aliases(facts, statement.id)
        and call.func.attr == "read_csv"
        and len(call.args) == 1
        and not call.keywords
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
        and "://" not in call.args[0].value
    ):
        return None
    path = call.args[0].value
    source = (
        path
        if PurePosixPath(path).is_absolute()
        else posixpath.normpath((PurePosixPath(facts.notebook.path).parent / path).as_posix())
    )
    matches = tuple(
        index
        for index, dataset in enumerate(plan.catalog_datasets)
        if dataset.name == node.targets[0].id
        and dataset.type == "kedro_datasets.pandas.CSVDataset"
        and dataset.filepath == f"data/01_raw/{PurePosixPath(source).name}"
        and dataset.source_filepath == source
    )
    return matches[0] if len(matches) == 1 else None


@dataclass(frozen=True, slots=True)
class _AccountingContext:
    facts: NotebookFacts
    plan: ConversionPlan
    owners: dict[str, list[str]]
    imports_match: bool


def _statement_record(
    context: _AccountingContext, cell_id: str, statement: StatementFacts
) -> tuple[StatementDisposition, int | None]:
    tasks = tuple(context.owners.get(statement.id, ()))
    imported = statement.ast_type in {"Import", "ImportFrom"}
    catalog = _catalog_claim(context.facts, statement, context.plan)
    disposition: StatementKind
    destinations: tuple[str, ...]
    claimed = None
    if imported and not tasks and context.imports_match:
        disposition, destinations = "module_import", ("shared_imports",)
        reason = "Preserved as an ordered shared import."
    elif catalog is not None and not tasks:
        disposition, destinations = "catalog", (context.plan.catalog_datasets[catalog].name,)
        reason = "Relocated exact option-free pandas CSV loading."
        claimed = catalog
    elif len(tasks) == 1 and not imported and catalog is None:
        disposition, destinations = "task", tasks
        reason = "Claimed by a task; checked against its declared source AST."
    else:
        disposition, destinations = "unhandled", tasks
        reason = "No single supported destination; preserve explicitly or reject."
    return StatementDisposition(statement.id, cell_id, disposition, destinations, reason), claimed


def _task_checks(facts: NotebookFacts, plan: ConversionPlan) -> tuple[PlanDiagnostic, ...]:
    ordered = {
        statement.id: (cell.id, statement) for cell in facts.cells for statement in cell.statements
    }
    positions = {statement_id: index for index, statement_id in enumerate(ordered)}
    diagnostics: list[PlanDiagnostic] = []
    for task in plan.task_candidates:
        if any(statement_id not in ordered for statement_id in task.statement_ids):
            diagnostics.append(
                _issue("SA002", "Task references unknown source statements.", task.id)
            )
            continue
        expected_cells = tuple(dict.fromkeys(ordered[item][0] for item in task.statement_ids))
        if (
            task.source_cell_ids != expected_cells
            or tuple(sorted(task.statement_ids, key=positions.__getitem__)) != task.statement_ids
        ):
            diagnostics.append(
                _issue("SA003", "Task provenance/order differs from source facts.", task.id)
            )
        source = "\n".join(ordered[item][1].source for item in task.statement_ids)
        try:
            matches = _tree(source) == _tree(task.source)
        except SyntaxError:
            matches = False
        if not matches:
            diagnostics.append(
                _issue("SA003", "Task source AST differs from its declared statements.", task.id)
            )
    return tuple(diagnostics)


def _graph_checks(
    facts: NotebookFacts, plan: ConversionPlan, records: tuple[StatementDisposition, ...]
) -> tuple[PlanDiagnostic, ...]:
    diagnostics: list[PlanDiagnostic] = []
    available = {dataset.name for dataset in plan.catalog_datasets}
    statements = {statement.id: statement for cell in facts.cells for statement in cell.statements}
    owners = {
        record.statement_id: record.destinations[0]
        for record in records
        if record.disposition == "task"
    }
    for task in plan.task_candidates:
        diagnostics.extend(
            _issue("SA006", f"Input {name} has no earlier task/catalog producer.", task.id)
            for name in task.inputs
            if name not in available
        )
        writes = {
            name
            for item in task.statement_ids
            if item in statements
            for name in statements[item].writes
        }
        if not set(task.outputs) <= writes:
            diagnostics.append(
                _issue("SA006", "Task outputs are not source-written symbols.", task.id)
            )
        diagnostics.extend(
            _issue("SA006", f"Missing source dependency input: {dependency.symbol}.", task.id)
            for dependency in facts.dependencies
            if (
                owners.get(dependency.consumer.statement_id) == task.id
                and owners.get(dependency.producer.statement_id) != task.id
                and dependency.symbol not in task.inputs
            )
        )
        available.update(task.outputs)
    diagnostics.extend(
        _issue("SA006", f"Unresolved source name: {diagnostic.related_symbol}.")
        for diagnostic in facts.diagnostics
        if diagnostic.code == "DF001"
    )
    return tuple(diagnostics)


def _parameter_checks(facts: NotebookFacts, plan: ConversionPlan) -> tuple[PlanDiagnostic, ...]:
    def values(candidate: ConversionPlan) -> Counter[tuple[str, str, str]]:
        return Counter(
            (
                parameter.source_cell_id,
                parameter.name.rsplit(".", maxsplit=1)[-1],
                json.dumps(parameter.value, sort_keys=True),
            )
            for parameter in candidate.parameters
        )

    diagnostics: list[PlanDiagnostic] = []
    if values(plan) != values(plan_tasks(facts)):
        diagnostics.append(
            _issue("SA007", "Extracted parameter values differ from deterministic source evidence.")
        )
    for parameter in plan.parameters:
        owners = tuple(task for task in plan.task_candidates if parameter.name in task.parameters)
        if (
            parameter.function_argument != parameter.name.replace(".", "_")
            or len(owners) != 1
            or parameter.source_cell_id not in owners[0].source_cell_ids
        ):
            diagnostics.append(
                _issue("SA007", f"Inconsistent parameter binding: {parameter.name}.")
            )
    return tuple(diagnostics)


def audit_conversion_source(facts: NotebookFacts, plan: ConversionPlan) -> ConversionSourceAudit:
    """Account for every parsed statement, without file, provider or execution I/O.

    Coverage is checked against supplied facts, not independently reacquired source bytes.
    A task statement and a hoisted import/catalog relocation cannot both claim one source
    instruction. Unhandled statements block conversion rather than being silently omitted.
    """
    diagnostics: list[PlanDiagnostic] = []
    try:
        validate_conversion_plan(plan)
    except ConversionPlanValidationError as error:
        diagnostics.append(_issue("SA001", str(error)))
    if facts.notebook.path != plan.notebook_path:
        diagnostics.append(_issue("SA001", "Plan notebook path differs from source facts."))
    if any(diagnostic.blocking for diagnostic in facts.diagnostics):
        diagnostics.append(
            _issue("SA000", "Blocking source diagnostics prevent complete accounting.")
        )
    original_imports = tuple(
        statement.source
        for cell in facts.cells
        for statement in cell.statements
        if statement.ast_type in {"Import", "ImportFrom"}
    )
    try:
        imports_match = tuple(map(_tree, original_imports)) == tuple(map(_tree, plan.imports))
    except SyntaxError:
        imports_match = False
    if not imports_match:
        diagnostics.append(
            _issue("SA005", "Shared imports differ from the original ordered imports.")
        )
    owners: dict[str, list[str]] = {}
    for task in plan.task_candidates:
        for statement_id in task.statement_ids:
            owners.setdefault(statement_id, []).append(task.id)
    records: list[StatementDisposition] = []
    catalog_claims: list[int] = []
    context = _AccountingContext(facts, plan, owners, imports_match)
    for cell in facts.cells:
        for statement in cell.statements:
            record, claimed = _statement_record(context, cell.id, statement)
            if claimed is not None:
                catalog_claims.append(claimed)
            if record.disposition == "unhandled":
                diagnostics.append(
                    _issue("SA002", f"Unhandled/duplicated statement {statement.id} in {cell.id}.")
                )
            records.append(record)
    if Counter(catalog_claims) != Counter(range(len(plan.catalog_datasets))):
        diagnostics.append(
            _issue(
                "SA004",
                "Catalog relocation is not one-to-one with exact option-free pandas CSV "
                "statements; check reader options, paths and mixed cells.",
            )
        )
    diagnostics.extend(_task_checks(facts, plan))
    diagnostics.extend(_graph_checks(facts, plan, tuple(records)))
    diagnostics.extend(_parameter_checks(facts, plan))
    return ConversionSourceAudit(
        facts.notebook.path,
        facts.notebook.content_sha256,
        _plan_sha256(plan),
        tuple(records),
        tuple(diagnostics),
    )


def enforce_source_accounting(facts: NotebookFacts, plan: ConversionPlan) -> ConversionPlan:
    """Add only failing audit diagnostics, preserving fully accounted legacy plan bytes."""
    audit = audit_conversion_source(facts, plan)
    if audit.complete:
        return plan
    return replace(
        plan,
        diagnostics=(*plan.diagnostics, *audit.diagnostics),
        blocking_diagnostic_codes=tuple(
            dict.fromkeys(
                (
                    *plan.blocking_diagnostic_codes,
                    *(diagnostic.code for diagnostic in audit.diagnostics),
                )
            )
        ),
    )

"""Bounded Pipeline alias hazards, using source bindings and proposed task ownership only."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from notebook_to_kedro.analysis.python_ast import qualified_name
from notebook_to_kedro.ir import PlanDiagnostic

if TYPE_CHECKING:
    from notebook_to_kedro.ir import ConversionPlan, NotebookFacts, StatementFacts


_STEP_PARTS = 2


def _components(call: ast.Call, imports: dict[str, str]) -> tuple[str, ...]:
    name = qualified_name(call.func)
    root, separator, suffix = name.partition(".")
    resolved = imports.get(root, "") + (separator + suffix)
    if resolved == "sklearn.pipeline.make_pipeline":
        return tuple(item.id for item in call.args if isinstance(item, ast.Name))
    if resolved != "sklearn.pipeline.Pipeline":
        return ()
    steps = (
        call.args[0]
        if call.args
        else next((keyword.value for keyword in call.keywords if keyword.arg == "steps"), None)
    )
    if not isinstance(steps, ast.List | ast.Tuple):
        return ()
    return tuple(
        item.elts[1].id
        for item in steps.elts
        if isinstance(item, ast.Tuple | ast.List)
        and len(item.elts) == _STEP_PARTS
        and isinstance(item.elts[1], ast.Name)
    )


@dataclass
class _AliasState:
    imports: dict[str, str] = field(default_factory=dict)
    bindings: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    pipelines: dict[str, tuple[tuple[str, ...], str | None]] = field(default_factory=dict)
    fitted: dict[str, tuple[str, str, str | None]] = field(default_factory=dict)
    reported: set[tuple[str, str]] = field(default_factory=set)

    def read_checks(self, statement: StatementFacts, owner: str | None) -> list[PlanDiagnostic]:
        diagnostics = []
        for name in dict.fromkeys(statement.reads):
            identity, binding_owner = self.bindings.get(name, ("", None))
            if identity in self.fitted and owner is not None:
                fit_owner, model, construction_owner = self.fitted[identity]
                key = (identity, owner)
                detached = construction_owner != fit_owner or fit_owner not in (
                    owner,
                    binding_owner,
                )
                if detached and key not in self.reported:
                    self.reported.add(key)
                    diagnostics.append(
                        PlanDiagnostic(
                            "SA009",
                            "error",
                            f"External Pipeline component alias {name!r} is read in "
                            f"{statement.id} after {model!r} was fitted in {fit_owner}. "
                            "Kedro memory copies can isolate its fitted state. Read the "
                            "fitted component owned by the returned model explicitly, "
                            "or keep construction, fitting and alias use in one task.",
                            owner,
                        )
                    )
        return diagnostics

    def value_identity(
        self, value: ast.expr | None, identity: str, owner: str | None
    ) -> tuple[str, str | None]:
        if isinstance(value, ast.Constant):
            return "", None
        if isinstance(value, ast.Name):
            return self.bindings.get(value.id, (identity, None))[0], self.imports.get(value.id)
        if isinstance(value, ast.Call):
            components = _components(value, self.imports)
            if components:
                self.pipelines[identity] = (
                    tuple(
                        self.bindings[name][0]
                        for name in components
                        if name in self.bindings and self.bindings[name][0]
                    ),
                    owner,
                )
            method = value.func
            if (
                isinstance(method, ast.Attribute)
                and isinstance(method.value, ast.Name)
                and method.attr in {"fit", "fit_transform", "fit_predict"}
                and owner is not None
            ):
                model = method.value.id
                model_id = self.bindings.get(model, ("", None))[0]
                components, construction_owner = self.pipelines.get(model_id, ((), None))
                for component in components:
                    self.fitted[component] = (owner, model, construction_owner)
                # Pipeline.fit returns self; the other two methods return transformed data.
                if method.attr == "fit" and model_id in self.pipelines:
                    identity = model_id
        return identity, None

    def advance(self, statement: StatementFacts, owner: str | None) -> None:
        node = ast.parse(statement.source).body[0]
        if isinstance(node, ast.AnnAssign) and node.value is None:
            return
        value: ast.expr | None = None
        target = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        elif isinstance(node, ast.Expr):
            value = node.value
        identity, imported = self.value_identity(value, statement.id, owner)
        for name in statement.writes:
            self.imports.pop(name, None)
            self.bindings.pop(name, None)
        if isinstance(target, ast.Name):
            self.bindings[target.id] = (identity, owner)
            if imported is not None:
                self.imports[target.id] = imported
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                self.imports[bound] = alias.name if alias.asname else bound
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            for alias in node.names:
                self.imports[alias.asname or alias.name] = f"{node.module}.{alias.name}"


def fitted_alias_checks(facts: NotebookFacts, plan: ConversionPlan) -> tuple[PlanDiagnostic, ...]:
    """Reject later external component reads after a named Pipeline fit crosses tasks.

    This is not general alias reconstruction. Only direct imports, named assignments, literal
    Pipeline steps/make_pipeline arguments and direct named fit calls are recognized. No source
    libraries are imported, source expressions evaluated, or runtime copy policies changed.
    """
    owners = {
        statement: task.id for task in plan.task_candidates for statement in task.statement_ids
    }
    state = _AliasState()
    diagnostics = []
    for cell in facts.cells:
        for statement in cell.statements:
            owner = owners.get(statement.id)
            diagnostics.extend(state.read_checks(statement, owner))
            state.advance(statement, owner)
    return tuple(diagnostics)

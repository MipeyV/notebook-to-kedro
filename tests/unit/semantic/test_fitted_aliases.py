"""Pipeline alias risks depend on original bindings and actual proposed task boundaries."""

from dataclasses import replace

import pytest

from notebook_to_kedro import audit_conversion_source
from notebook_to_kedro.analysis import analyze_notebook
from notebook_to_kedro.ir import NotebookFacts
from notebook_to_kedro.notebook import LoadedCell, LoadedNotebook, NotebookCellKind
from notebook_to_kedro.semantic import plan_tasks
from notebook_to_kedro.semantic.fitted_aliases import fitted_alias_checks


def _facts(*sources: str) -> NotebookFacts:
    return analyze_notebook(
        LoadedNotebook(
            "aliases.ipynb",
            4,
            5,
            "python",
            "python3",
            "a" * 64,
            tuple(
                LoadedCell(f"cell-{i:04d}", i, NotebookCellKind.CODE, s)
                for i, s in enumerate(sources)
            ),
        )
    )


@pytest.mark.parametrize(
    ("imports", "constructor"),
    [
        ("from sklearn.pipeline import Pipeline", "Pipeline([('prepare', preprocessor)])"),
        ("from sklearn.pipeline import Pipeline as Chain", "Chain(steps=(('p', preprocessor),))"),
        ("import sklearn.pipeline as sp", "sp.Pipeline([['p', preprocessor]])"),
        ("import sklearn.pipeline", "sklearn.pipeline.Pipeline([('p', preprocessor)])"),
        ("import sklearn", "sklearn.pipeline.Pipeline([('p', preprocessor)])"),
        ("from sklearn.pipeline import make_pipeline", "make_pipeline(preprocessor)"),
    ],
)
@pytest.mark.parametrize(
    "fit",
    [
        "model.fit(X)",
        "model = model.fit(X)",
        "data = model.fit_transform(X)",
        "data = model.fit_predict(X)",
    ],
)
def test_import_resolved_pipeline_components_block_external_reads(
    imports: str, constructor: str, fit: str
) -> None:
    facts = _facts(
        imports,
        "preprocessor = object()\nX = [[1], [2]]",
        f"model = {constructor}\n{fit}",
        "result = preprocessor",
    )
    before = facts.to_json()
    plan = plan_tasks(facts)
    audit = audit_conversion_source(facts, plan)
    assert {item.code for item in audit.diagnostics} == {"SA009"}
    issue = audit.diagnostics[0]
    assert issue.task_id == plan.task_candidates[-1].id
    assert "preprocessor" in issue.message
    assert "cell-0003-stmt-0000" in issue.message
    assert facts.to_json() == before
    assert audit.to_json() == audit_conversion_source(facts, plan).to_json()


@pytest.mark.parametrize("alias", ["before", "inside"])
def test_direct_component_and_model_aliases_respect_binding_ownership(alias: str) -> None:
    creation = "preprocessor = object()\nX = [[1], [2]]"
    training = "model = Pipeline([('p', preprocessor)])\nrenamed = model\nrenamed.fit(X)"
    if alias == "before":
        creation += "\nexternal = preprocessor"
    else:
        training = "external = preprocessor\n" + training
    facts = _facts("from sklearn.pipeline import Pipeline", creation, training, "result = external")
    audit = audit_conversion_source(facts, plan_tasks(facts))
    assert {item.code for item in audit.diagnostics} == ({"SA009"} if alias == "before" else set())


@pytest.mark.parametrize(
    ("training", "report"),
    [
        ("model.fit(X)", "result = model.named_steps['p']"),
        ("model.fit(X)\nresult = preprocessor", "final = result"),
        ("model.fit(X)\npreprocessor = model.named_steps['p']", "result = preprocessor"),
        ("model.fit(X)", "preprocessor = object()\nresult = preprocessor"),
        ("scores = model.predict(X)", "result = preprocessor"),
    ],
)
def test_model_owned_components_local_use_rebinding_and_nonfit_calls_stay_eligible(
    training: str, report: str
) -> None:
    facts = _facts(
        "from sklearn.pipeline import Pipeline",
        "preprocessor = object()\nX = [[1], [2]]",
        "model = Pipeline([('p', preprocessor)])\n" + training,
        report,
    )
    assert audit_conversion_source(facts, plan_tasks(facts)).complete


def test_construction_fitting_and_export_in_one_task_is_not_a_stale_prototype() -> None:
    facts = _facts(
        "from sklearn.pipeline import Pipeline",
        "preprocessor = object()\nX = [[1], [2]]\n"
        "model = Pipeline([('p', preprocessor)])\nmodel.fit(X)",
        "result = preprocessor",
    )
    assert audit_conversion_source(facts, plan_tasks(facts)).complete


@pytest.mark.parametrize(
    ("imports", "constructor"),
    [
        ("from other_library import Pipeline", "Pipeline([('p', preprocessor)])"),
        ("from .sklearn.pipeline import Pipeline", "Pipeline([('p', preprocessor)])"),
        ("from sklearn.pipeline import Pipeline", "Pipeline(steps)"),
        ("from sklearn.pipeline import Pipeline", "Pipeline()"),
        ("from sklearn.pipeline import Pipeline", "Pipeline([('p', object()), ('p',), 2])"),
    ],
)
def test_unresolved_factories_and_dynamic_steps_do_not_acquire_library_semantics(
    imports: str, constructor: str
) -> None:
    facts = _facts(
        imports,
        "preprocessor = object()\nsteps = [('p', preprocessor)]\nX = [[1]]",
        f"model = {constructor}\nmodel.fit(X)",
        "result = preprocessor",
    )
    assert not fitted_alias_checks(facts, plan_tasks(facts))


def test_import_alias_assignment_and_later_import_shadowing_are_source_ordered() -> None:
    imports = "from sklearn.pipeline import Pipeline"
    creation = "preprocessor = object()\nX = [[1]]\nFactory = Pipeline\nPipeline = object"
    training = "model: object = Factory(steps=[('p', preprocessor)])\nmodel.fit(X)"
    facts = _facts(imports, creation, training, "result = preprocessor")
    assert {item.code for item in fitted_alias_checks(facts, plan_tasks(facts))} == {"SA009"}
    facts = _facts(
        imports, creation, training.replace("Factory(", "Pipeline("), "result = preprocessor"
    )
    assert not fitted_alias_checks(facts, plan_tasks(facts))


def test_duplicate_reads_report_one_task_hazard_and_distinct_tasks_remain_visible() -> None:
    facts = _facts(
        "from sklearn.pipeline import Pipeline",
        "preprocessor = object()\nX = [[1]]",
        "model = Pipeline([('p', preprocessor)])\nmodel.fit(X)",
        "a = preprocessor\nb = preprocessor",
        "c = preprocessor",
    )
    plan = plan_tasks(facts)
    issues = fitted_alias_checks(facts, plan)
    assert len(issues) == 2
    assert issues[0].task_id != issues[1].task_id
    # Unknown/duplicated task ownership is independently rejected by the main audit.
    assert not fitted_alias_checks(facts, replace(plan, task_candidates=()))


def test_unrecognized_assignment_forms_do_not_invent_component_identities() -> None:
    facts = _facts(
        "from sklearn.pipeline import Pipeline",
        "a = b = object()\nX = [[1]]\nempty: object",
        "model = Pipeline([('a', a), ('b', b)])\nmodel.fit(X)",
        "result = a",
    )
    assert not fitted_alias_checks(facts, plan_tasks(facts))


@pytest.mark.parametrize("reuse", ["inside_fit", "after_fit", "local_alias_export"])
def test_pipeline_built_in_an_earlier_task_cannot_share_a_separately_loaded_prototype(
    reuse: str,
) -> None:
    fit = "model = model.fit(X)"
    report = "result = preprocessor"
    if reuse == "inside_fit":
        fit += "\nresult = preprocessor"
        report = "final = result"
    elif reuse == "local_alias_export":
        fit = "external = preprocessor\n" + fit
        report = "result = external"
    facts = _facts(
        "from sklearn.pipeline import Pipeline",
        "preprocessor = object()\nX = [[1]]\nmodel = Pipeline([('p', preprocessor)])",
        fit,
        report,
    )
    issues = fitted_alias_checks(facts, plan_tasks(facts))
    assert len(issues) == (2 if reuse == "inside_fit" else 1)
    assert {issue.code for issue in issues} == {"SA009"}


@pytest.mark.parametrize("constant", ["None", "'passthrough'"])
def test_disabled_or_passthrough_steps_have_no_fitted_object_alias(constant: str) -> None:
    facts = _facts(
        "from sklearn.pipeline import Pipeline",
        f"preprocessor = {constant}\nexternal = preprocessor\nX = [[1]]",
        "model = Pipeline([('p', external)])\nmodel.fit(X)",
        "result = external",
    )
    assert audit_conversion_source(facts, plan_tasks(facts)).complete


def test_annotation_without_a_value_does_not_rebind_an_existing_alias() -> None:
    facts = _facts(
        "from sklearn.pipeline import Pipeline",
        "preprocessor = object()\nX = [[1]]",
        "model = Pipeline([('p', preprocessor)])\nmodel.fit(X)",
        "preprocessor: object\nresult = preprocessor",
    )
    assert {issue.code for issue in fitted_alias_checks(facts, plan_tasks(facts))} == {"SA009"}


def test_a_faithful_merged_task_uses_actual_ownership_instead_of_original_cell_boundaries() -> None:
    facts = _facts(
        "from sklearn.pipeline import Pipeline",
        "preprocessor = object()\nX = [[1]]",
        "model = Pipeline([('p', preprocessor)])\nmodel.fit(X)",
        "result = preprocessor",
    )
    plan = plan_tasks(facts)
    assert fitted_alias_checks(facts, plan)
    tasks = plan.task_candidates
    merged = replace(
        tasks[0],
        id="merged",
        name="whole_workflow",
        source_cell_ids=tuple(cell for task in tasks for cell in task.source_cell_ids),
        statement_ids=tuple(statement for task in tasks for statement in task.statement_ids),
        inputs=(),
        outputs=("result",),
        source="\n".join(task.source for task in tasks),
    )
    assert audit_conversion_source(facts, replace(plan, task_candidates=(merged,))).complete

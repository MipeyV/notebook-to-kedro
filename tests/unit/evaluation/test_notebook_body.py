"""Pure recorded-response batches never call providers, execute code or write projects."""

from __future__ import annotations

import ast
import json
from dataclasses import replace
from typing import Any

import pytest

from notebook_to_kedro.evaluation import (
    NotebookBodyRecord,
    prepare_notebook_body_requests,
    validate_notebook_body_batch,
)
from notebook_to_kedro.evaluation import notebook_body as batch_module
from notebook_to_kedro.generation.code import NodeBodyResponse
from notebook_to_kedro.ir import CatalogDataset, ConversionPlan, ParameterValue, TaskCandidate


@pytest.fixture
def plan() -> ConversionPlan:
    return ConversionPlan(
        "1.0",
        "test",
        "not-read.ipynb",
        (
            TaskCandidate("a", "create_values", ("c1",), ("s1",), (), ("values",), "values = [1]"),
            TaskCandidate(
                "b",
                "count_values",
                ("c2",),
                ("s2",),
                ("values",),
                ("count",),
                "count = len(values)",
            ),
        ),
    )


def _records(plan: ConversionPlan) -> tuple[NotebookBodyRecord, ...]:
    return tuple(
        NotebookBodyRecord(
            request.request_id,
            "\n "
            + NodeBodyResponse(
                "1.0", request.request_id, request.task_id, request.raw_source
            ).to_json(),
        )
        for request in prepare_notebook_body_requests(plan)
    )


def test_complete_batch_is_static_and_retains_exact_records(
    plan: ConversionPlan, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = _records(plan)

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("static validation must not execute, contact providers or write files")

    monkeypatch.setattr("builtins.exec", forbidden)
    monkeypatch.setattr("pathlib.Path.write_text", forbidden)
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    report = validate_notebook_body_batch(plan, tuple(reversed(records)))
    assert report.planned_count == report.accepted_count == 2
    assert report.static_ready
    assert [proposal.record for proposal in report.proposals] == list(records)
    assert all(proposal.status == "accepted" for proposal in report.proposals)
    assert report.module_source is not None
    functions = ast.parse(report.module_source).body
    assert [node.name for node in functions if isinstance(node, ast.FunctionDef)] == [
        "create_values",
        "count_values",
    ]
    assert len(report.plan_sha256) == 64
    assert report.plan_sha256 == validate_notebook_body_batch(plan, records).plan_sha256
    changed = replace(plan, notebook_path="different.ipynb")
    assert report.plan_sha256 != validate_notebook_body_batch(changed, records).plan_sha256


def test_all_empty_slots_stay_in_denominator(plan: ConversionPlan) -> None:
    report = validate_notebook_body_batch(plan, ())
    assert report.planned_count == 2
    assert report.accepted_count == 0
    assert not report.static_ready
    assert report.module_source is None
    assert [proposal.status for proposal in report.proposals] == ["not_requested"] * 2
    assert all(proposal.record is None for proposal in report.proposals)


@pytest.mark.parametrize(
    ("record_kwargs", "status", "code"),
    [
        ({"provider_error": ("offline_error", "fixed failure")}, "provider_error", "offline_error"),
        ({"raw_response": "not json"}, "invalid_response", "invalid_response"),
        ({"raw_response": ""}, "invalid_response", "invalid_response"),
        ({"raw_response": "\ud800"}, "invalid_response", "invalid_utf8"),
    ],
)
def test_failures_preserve_one_slot_and_other_acceptances(
    plan: ConversionPlan, record_kwargs: dict[str, Any], status: str, code: str
) -> None:
    records = _records(plan)
    failed = NotebookBodyRecord(records[0].request_id, **record_kwargs)
    report = validate_notebook_body_batch(plan, (failed, records[1]))
    assert report.accepted_count == 1
    assert report.planned_count == 2
    assert not report.static_ready
    proposal = report.proposals[0]
    assert proposal.status == status
    assert proposal.diagnostic_code == code
    assert proposal.diagnostic_message
    assert proposal.record == failed
    assert proposal.body is None
    assert proposal.response is None


@pytest.mark.parametrize("changed_body", ["values = [2]", "this is (", "return [1]"])
def test_semantic_syntax_and_return_rejections_disable_complete_module(
    plan: ConversionPlan, changed_body: str
) -> None:
    records = _records(plan)
    request = prepare_notebook_body_requests(plan)[0]
    record = NotebookBodyRecord(
        request.request_id,
        NodeBodyResponse("1.0", request.request_id, request.task_id, changed_body).to_json(),
    )
    report = validate_notebook_body_batch(plan, (record, records[1]))
    assert not report.static_ready
    assert report.accepted_count == 1
    proposal = report.proposals[0]
    assert proposal.status == proposal.diagnostic_code == "invalid_code"
    assert proposal.body is not None
    assert proposal.response is None
    assert proposal.record == record


def test_wrong_embedded_identity_is_rejected(plan: ConversionPlan) -> None:
    records = _records(plan)
    data = json.loads(records[0].raw_response or "")
    data["request_id"] = "different"
    report = validate_notebook_body_batch(
        plan, (NotebookBodyRecord(records[0].request_id, json.dumps(data)), records[1])
    )
    assert report.proposals[0].status == "invalid_code"
    assert report.module_source is None


def test_response_byte_limit_is_utf8_and_does_not_parse_oversized_text(
    plan: ConversionPlan, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = NotebookBodyRecord("notebook-body:a", "\u00e9")

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("oversized responses must not be parsed")

    monkeypatch.setattr(NodeBodyResponse, "from_json", forbidden)
    report = validate_notebook_body_batch(plan, (record,), max_response_bytes=1)
    proposal = report.proposals[0]
    assert proposal.status == "invalid_response"
    assert proposal.diagnostic_code == "response_too_large"
    assert proposal.record == record


@pytest.mark.parametrize("limit", [True, 0, -1, 1.5])
def test_bad_response_limits(plan: ConversionPlan, limit: Any) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        validate_notebook_body_batch(plan, (), max_response_bytes=limit)


@pytest.mark.parametrize("duplicate", [False, True])
def test_unknown_and_duplicate_record_ids_fail_before_parsing(
    plan: ConversionPlan, monkeypatch: pytest.MonkeyPatch, *, duplicate: bool
) -> None:
    record = NotebookBodyRecord("notebook-body:a" if duplicate else "unknown", "bad")

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("record inventory must be validated first")

    monkeypatch.setattr(batch_module, "_validate_record", forbidden)
    with pytest.raises(ValueError, match="duplicate" if duplicate else "unknown"):
        validate_notebook_body_batch(plan, (record, record) if duplicate else (record,))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"request_id": " "},
        {"request_id": 1},
        {},
        {"raw_response": "{}", "provider_error": ("code", "message")},
        {"raw_response": 1},
        {"provider_error": ("", "message")},
        {"provider_error": ("code", "")},
        {"provider_error": ("code", 1)},
        {"provider_error": ("code",)},
        {"provider_error": ["code", "message"]},
    ],
)
def test_invalid_record_contract(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"record|provider_error"):
        NotebookBodyRecord(**{"request_id": "a", **kwargs})


@pytest.mark.parametrize("prefix", ["", " ", 1])
def test_invalid_prefix(plan: ConversionPlan, prefix: Any) -> None:
    with pytest.raises(ValueError, match="request_prefix"):
        prepare_notebook_body_requests(plan, request_prefix=prefix)


def test_custom_prefix_is_bound_to_record_ids(plan: ConversionPlan) -> None:
    requests = prepare_notebook_body_requests(plan, request_prefix="attempt-1")
    assert requests[0].request_id == "attempt-1:a"
    records = tuple(
        NotebookBodyRecord(
            request.request_id,
            NodeBodyResponse(
                "1.0", request.request_id, request.task_id, request.raw_source
            ).to_json(),
        )
        for request in requests
    )
    assert validate_notebook_body_batch(plan, records, request_prefix="attempt-1").static_ready


def test_empty_and_blocked_plans(plan: ConversionPlan) -> None:
    with pytest.raises(ValueError, match="at least one task"):
        prepare_notebook_body_requests(replace(plan, task_candidates=()))
    with pytest.raises(ValueError, match="blocking diagnostics"):
        prepare_notebook_body_requests(replace(plan, blocking_diagnostic_codes=("blocked",)))


@pytest.mark.parametrize("kind", ["statement", "output", "catalog", "missing", "cycle", "self"])
def test_ambiguous_or_invalid_graph(plan: ConversionPlan, kind: str) -> None:
    first, second = plan.task_candidates
    datasets: tuple[CatalogDataset, ...] = ()
    expected = "multiple producers"
    if kind == "statement":
        second = replace(second, statement_ids=first.statement_ids)
        expected = "multiple tasks"
    elif kind == "output":
        second = replace(second, outputs=first.outputs)
    elif kind == "catalog":
        datasets = (CatalogDataset("values", "example", "unused.csv"),)
    elif kind == "missing":
        second = replace(second, inputs=("missing",))
        expected = "unresolved"
    elif kind == "cycle":
        first = replace(first, inputs=("count",))
        expected = "acyclic"
    else:
        first = replace(first, inputs=("values",))
        expected = "acyclic"
    with pytest.raises(ValueError, match=expected):
        prepare_notebook_body_requests(
            replace(plan, task_candidates=(first, second), catalog_datasets=datasets)
        )


def test_catalog_roots_and_topologically_reordered_tasks_are_valid(plan: ConversionPlan) -> None:
    _, second = plan.task_candidates
    catalog = CatalogDataset("values", "example", "never-opened.csv")
    rooted = replace(plan, task_candidates=(second,), catalog_datasets=(catalog,))
    assert len(prepare_notebook_body_requests(rooted)) == 1
    reordered = replace(plan, task_candidates=tuple(reversed(plan.task_candidates)))
    assert [request.task_id for request in prepare_notebook_body_requests(reordered)] == ["b", "a"]


@pytest.mark.parametrize("source", ["import (", "values = 1", "import math\nimport os"])
def test_invalid_shared_imports_are_rejected(plan: ConversionPlan, source: str) -> None:
    with pytest.raises(ValueError, match="one valid import"):
        prepare_notebook_body_requests(replace(plan, imports=(source,)))


@pytest.mark.parametrize("name", ["len", "math", "join", "path", "np"])
def test_node_names_cannot_shadow_shared_globals(plan: ConversionPlan, name: str) -> None:
    first, second = plan.task_candidates
    imports = (
        "import math",
        "from os.path import join",
        "import os.path",
        "import numpy as np",
        "from os import path",
    )
    with pytest.raises(ValueError, match="shadow"):
        prepare_notebook_body_requests(
            replace(plan, task_candidates=(replace(first, name=name), second), imports=imports)
        )


def test_complete_module_preserves_original_shared_import_order(plan: ConversionPlan) -> None:
    first, second = plan.task_candidates
    first = replace(first, source="values = [math.floor(1.2)]")
    second = replace(second, source="count = math.floor(len(values))")
    changed = replace(
        plan,
        task_candidates=(first, second),
        imports=("import math", "from os import path as alias"),
    )
    report = validate_notebook_body_batch(changed, _records(changed))
    assert report.module_source is not None
    assert report.module_source.count("import math") == 1
    assert report.module_source.startswith("import math\n\nfrom os import path as alias\n\n")


@pytest.mark.parametrize("source", ["from os import *", "from . import path"])
def test_relative_and_wildcard_imports_fail_preflight(plan: ConversionPlan, source: str) -> None:
    with pytest.raises(ValueError, match="relative and wildcard"):
        prepare_notebook_body_requests(replace(plan, imports=(source,)))


def test_shared_imports_must_compile_in_original_order(plan: ConversionPlan) -> None:
    imports = ("import math", "from __future__ import annotations")
    with pytest.raises(ValueError, match="compile together"):
        prepare_notebook_body_requests(replace(plan, imports=imports))


def test_all_parameter_evidence_preflights_before_caller_can_request(plan: ConversionPlan) -> None:
    first, second = plan.task_candidates
    first = replace(
        first, source="values = frame.fillna(0)", inputs=("frame",), parameters=("fill",)
    )
    parameter = ParameterValue("fill", 0, "fill_value", "c1")
    changed = replace(
        plan,
        task_candidates=(first, second),
        catalog_datasets=(CatalogDataset("frame", "example", "unused.csv"),),
        parameters=(parameter,),
    )
    with pytest.raises(ValueError, match="exactly one"):
        prepare_notebook_body_requests(changed)


def test_nonfinite_plan_identity_is_rejected(plan: ConversionPlan) -> None:
    changed = replace(plan, parameters=(ParameterValue("unused", float("nan"), "unused", "c1"),))
    with pytest.raises(ValueError, match="JSON compliant"):
        validate_notebook_body_batch(changed, ())

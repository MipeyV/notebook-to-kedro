"""Synthetic declarations exercise review gates; none are real human approval."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

import nbformat
import pytest

from notebook_to_kedro import plan_notebook_path
from notebook_to_kedro.evaluation import (
    BehavioralExecutionConfig,
    ComparisonSpec,
    ExpectedBehaviorOutput,
    NotebookBodyRecord,
    NotebookCampaignInputs,
    NotebookObservation,
    NotebookOllamaControls,
    NotebookOllamaResponse,
    NotebookOllamaSettings,
    NotebookPipelineArtifact,
    NotebookPipelineRun,
    NotebookSourceBinding,
    ScalarBehaviorValue,
    collect_notebook_runtime_identity,
    create_notebook_body_capture,
    create_notebook_campaign,
    create_notebook_ollama_controls,
    create_notebook_pipeline_artifact,
    create_notebook_source_binding,
    load_notebook_body_capture,
    load_notebook_campaign,
    notebook_campaign_summary,
    prepare_notebook_campaign,
    record_notebook_body_response,
    record_notebook_campaign_response,
    replay_notebook_body_capture,
    reserve_notebook_body_request,
    reserve_notebook_campaign_request,
    write_notebook_pipeline_artifact,
)
from notebook_to_kedro.evaluation import notebook_review as review
from notebook_to_kedro.evaluation.behavioral_artifacts import write_json_exclusive
from notebook_to_kedro.evaluation.behavioral_execution import _result_from_worker
from notebook_to_kedro.evaluation.notebook_execution import NOTEBOOK_PIPELINE_EXECUTION_VERSION
from notebook_to_kedro.exceptions import BehavioralBenchmarkArtifactError
from notebook_to_kedro.generation.code import NodeBodyResponse
from notebook_to_kedro.generation.code.body_prompting import render_node_body_prompt

ROOT = Path(__file__).resolve().parents[3]
EXPECTED = (ExpectedBehaviorOutput("accuracy", ScalarBehaviorValue(1.0), ComparisonSpec("exact")),)


@dataclass
class _Fixture:
    root: Path
    binding: NotebookSourceBinding
    capture: Path
    baseline: NotebookPipelineArtifact
    baseline_path: Path

    def pending(self) -> review.NotebookHumanReview:
        return review.prepare_notebook_human_review(
            self.baseline, fixture_author_ids=("synthetic-author",)
        )

    def decision(self) -> dict[str, Any]:
        return {
            "reviewer_id": "synthetic-test-reviewer-not-a-real-review",
            "reviewer_kind": "human",
            "independent_human_review": True,
            "review_date": "2026-10-12",
            "reviewed_revision": "1" * 40,
            "decision": "approved",
            "checks": [
                {"section": section, "completed": True, "notes": "Synthetic test declaration only."}
                for section in review.NOTEBOOK_REVIEW_SECTIONS
            ],
            "corrections": "None; synthetic unit-test data, not actual review.",
            "evidence_reference": "synthetic:test-only",
            "evidence_path": "proof.md",
        }

    def recorded(self, **changes: Any) -> review.NotebookHumanReview:
        return review.record_notebook_human_review(
            self.pending(), {**self.decision(), **changes}, project_root=self.root
        )

    def promote(
        self, record: review.NotebookHumanReview, **kwargs: Any
    ) -> review.ReviewedNotebookContract:
        path = self.root / "decision.json"
        review.write_notebook_human_review(path, record)
        return review.promote_notebook_pipeline_artifact(
            self.baseline_path,
            self.binding,
            self.capture,
            path,
            project_root=self.root,
            operator_id="synthetic-test-operator",
            accept_human_review_evidence=True,
            **kwargs,
        )


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> _Fixture:
    root = tmp_path_factory.mktemp("synthetic-review")
    factory = cast("Any", nbformat.v4)
    notebook = factory.new_notebook(
        metadata={"language_info": {"name": "python"}},
        cells=[
            factory.new_markdown_cell("# Reference fixture", id="title"),
            factory.new_code_cell("import math", id="imports"),
            factory.new_markdown_cell("## Simulate reference", id="section"),
            factory.new_code_cell("accuracy = math.sqrt(1.0)", id="simulate"),
        ],
    )
    source = root / "reference.ipynb"
    source.write_text(cast("Any", nbformat).writes(notebook), encoding="utf-8")
    contract = {
        "schema_version": "pilot-draft-1",
        "case_id": "synthetic-review-unit-test",
        "review": {
            "status": "pending",
            "independent_human_review": False,
            "reviewed_by": None,
            "provenance": "Synthetic unit-test fixture, never real human review.",
            "local_benchmark_provider_exposure": "none",
        },
        "notebook": {
            "path": source.name,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
        "sources": [{"name": "accuracy", "kind": "simulation", "catalog_entry": False}],
    }
    (root / "contract.json").write_text(json.dumps(contract), encoding="utf-8")
    (root / "catalog.yml").write_text("{}\n", encoding="utf-8")
    (root / "proof.md").write_text(
        "Synthetic unit-test proof only. No human review occurred.\n", encoding="utf-8"
    )
    binding = create_notebook_source_binding(
        plan_notebook_path(source, project_root=root),
        project_root=root,
        contract_path="contract.json",
        expected_catalog_path="catalog.yml",
    )
    directory = create_notebook_body_capture(
        root / "capture",
        binding,
        project_root=root,
        provider_name="offline",
        model_name="synthetic-unit-test",
        prompt_version="fixture-1",
    )
    for request in binding.requests:
        reserve_notebook_body_request(directory, binding, request.request_id, project_root=root)
        record_notebook_body_response(
            directory,
            binding,
            NotebookBodyRecord(
                request.request_id,
                NodeBodyResponse(
                    "1.0", request.request_id, request.task_id, request.raw_source
                ).to_json(),
            ),
            project_root=root,
        )
    capture = load_notebook_body_capture(directory, binding, project_root=root)
    static = replay_notebook_body_capture(directory, binding, project_root=root)
    assert static.batch.module_source is not None
    identity = collect_notebook_runtime_identity(ROOT)
    # Typed transport is fabricated only for isolated gate tests, never published as pilot evidence.
    result = _result_from_worker(
        {
            "schema_version": "1.0",
            "case_id": binding.case_id,
            "node_code_case_id": capture.content_sha256,
            "status": "success",
            "outputs": [{"output_name": "accuracy", "value": {"kind": "scalar", "value": 1.0}}],
            "exception": None,
            "stdout": "",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "diagnostic_message": None,
        },
        0.0,
    )
    run = NotebookPipelineRun(
        NOTEBOOK_PIPELINE_EXECUTION_VERSION,
        capture,
        static,
        (NotebookObservation("accuracy"),),
        BehavioralExecutionConfig(),
        hashlib.sha256(static.batch.module_source.encode()).hexdigest(),
        "2" * 64,
        result,
        identity,
        identity,
    )
    baseline = create_notebook_pipeline_artifact(run, EXPECTED)
    path = write_notebook_pipeline_artifact(root / "baseline.json", baseline)
    return _Fixture(root, binding, directory, baseline, path)


@pytest.fixture
def fixture(tmp_path: Path, base: _Fixture) -> _Fixture:
    # Project-relative bindings can be checked unchanged in a copied root.
    root = tmp_path / "project"
    shutil.copytree(base.root, root)
    return _Fixture(root, base.binding, root / "capture", base.baseline, root / "baseline.json")


def _save_payload(path: Path, payload: dict[str, Any]) -> None:
    write_json_exclusive(path, review._seal(payload))


def test_pending_request_has_no_approval_or_checked_boxes(fixture: _Fixture) -> None:
    request = fixture.pending()
    assert request.decision == "pending"
    assert request.reviewer_id is None
    assert request.reviewer_kind is None
    assert not request.independent_human_review
    assert request.evidence_file is None
    assert all(not check.completed and check.notes == "" for check in request.checks)
    assert request.source_binding_sha256 == fixture.binding.content_sha256
    assert request.expectations_sha256 == fixture.baseline.comparison.expectations_sha256
    path = review.write_notebook_human_review(fixture.root / "pending.json", request)
    assert review.load_notebook_human_review(path, project_root=fixture.root) == request
    with pytest.raises(ValueError, match="approved independent human"):
        fixture.promote(request)
    assert json.loads((fixture.root / "contract.json").read_text())["review"]["status"] == "pending"


def test_synthetic_positive_gate_publishes_separate_wrapper_only(
    fixture: _Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_a: Any, **_k: Any) -> None:
        pytest.fail("review must never execute code or contact a provider")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("notebook_to_kedro.evaluation.notebook_execution._start_worker", forbidden)
    original = fixture.baseline_path.read_bytes()
    source = (fixture.root / "contract.json").read_bytes()
    record = fixture.recorded()
    wrapper = fixture.promote(record)
    path = review.write_reviewed_notebook_contract(fixture.root / "reviewed.json", wrapper)
    loaded = review.load_reviewed_notebook_contract(
        path, fixture.baseline_path, fixture.binding, fixture.capture, project_root=fixture.root
    )
    assert loaded == wrapper
    assert loaded.baseline.expectations == EXPECTED
    assert loaded.review.evidence_file is not None
    assert loaded.review.evidence_file.path == "proof.md"
    assert loaded.operator_id == "synthetic-test-operator"
    assert fixture.baseline_path.read_bytes() == original
    assert (fixture.root / "contract.json").read_bytes() == source
    with pytest.raises(BehavioralBenchmarkArtifactError, match="already exists"):
        review.write_reviewed_notebook_contract(path, wrapper)
    with pytest.raises(ValueError, match="cannot be amended"):
        review.record_notebook_human_review(record, fixture.decision(), project_root=fixture.root)


@pytest.mark.parametrize("consent", [False, None, 1])
def test_promotion_requires_operator_acceptance_before_io(base: _Fixture, consent: Any) -> None:
    with pytest.raises(ValueError, match="accept_human_review_evidence"):
        review.promote_notebook_pipeline_artifact(
            "missing",
            base.binding,
            "missing",
            "missing",
            project_root="missing",
            operator_id="test",
            accept_human_review_evidence=consent,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("decision", "changes_requested", "approved independent"),
        ("decision", "pending", "approved independent"),
        ("reviewer_kind", "model", "approved independent"),
        ("independent_human_review", False, "approved independent"),
        ("reviewer_id", " SYNTHETIC-AUTHOR ", "fixture author"),
        ("reviewer_id", None, "complete reviewer"),
        ("review_date", None, "complete reviewer"),
        ("reviewed_revision", None, "complete reviewer"),
        ("corrections", None, "complete reviewer"),
        ("evidence_reference", None, "complete reviewer"),
        ("evidence_path", None, "complete reviewer"),
    ],
)
def test_declared_approval_is_not_enough(
    fixture: _Fixture, field: str, value: Any, message: str
) -> None:
    record = fixture.recorded(**{field: value})
    assert (
        review.load_notebook_human_review(
            review.write_notebook_human_review(fixture.root / "inspect.json", record),
            project_root=fixture.root,
        )
        == record
    )
    with pytest.raises(ValueError, match=message):
        fixture.promote(record)


def test_every_review_section_is_required(fixture: _Fixture) -> None:
    decision = fixture.decision()
    decision["checks"][1].update(completed=False, notes="Changes requested in synthetic test.")
    with pytest.raises(ValueError, match="every worksheet section"):
        fixture.promote(
            review.record_notebook_human_review(
                fixture.pending(), decision, project_root=fixture.root
            )
        )


@pytest.mark.parametrize(
    "field", ["baseline_artifact_sha256", "source_binding_sha256", "expectations_sha256"]
)
def test_review_for_different_bytes_is_refused(fixture: _Fixture, field: str) -> None:
    payload = review.notebook_human_review_to_dict(fixture.recorded())
    payload[field] = "0" * 64
    _save_payload(fixture.root / "wrong.json", payload)
    record = review.load_notebook_human_review(
        fixture.root / "wrong.json", project_root=fixture.root
    )
    with pytest.raises(ValueError, match="exact reference, sources and expectations"):
        fixture.promote(record)


@pytest.mark.parametrize("mode", ["blocked", "mismatch", "subset", "unknown", "drift"])
def test_reference_preflight_does_not_infer_readiness(base: _Fixture, mode: str) -> None:
    baseline = base.baseline
    if mode == "blocked":
        static = replace(
            baseline.run.static, batch=replace(baseline.run.static.batch, module_source=None)
        )
        run = replace(
            baseline.run, static=static, execution=None, request_sha256=None, module_sha256=None
        )
        baseline = create_notebook_pipeline_artifact(run, EXPECTED)
    elif mode == "mismatch":
        baseline = create_notebook_pipeline_artifact(
            baseline.run, (replace(EXPECTED[0], value=ScalarBehaviorValue(0.0)),)
        )
    elif mode == "subset":
        task = baseline.run.capture.binding.plan.task_candidates[0]
        altered_plan = replace(
            baseline.run.capture.binding.plan,
            task_candidates=(replace(task, outputs=(*task.outputs, "unobserved")),),
        )
        binding = replace(baseline.run.capture.binding, plan=altered_plan)
        run = replace(
            baseline.run,
            capture=replace(baseline.run.capture, binding=binding),
            static=replace(baseline.run.static, binding=binding),
        )
        baseline = create_notebook_pipeline_artifact(run, EXPECTED)
    else:
        before = baseline.run.runtime_before
        assert before is not None
        changed = (
            replace(before, lock_sha256=None)
            if mode == "unknown"
            else replace(before, python_version="changed")
        )
        baseline = create_notebook_pipeline_artifact(
            replace(baseline.run, runtime_after=changed), EXPECTED
        )
    with pytest.raises(ValueError, match=r"matched complete|runtime compatibility"):
        review.prepare_notebook_human_review(baseline, fixture_author_ids=("test",))


@pytest.mark.parametrize("mode", ["changed", "missing", "escape"])
def test_proof_drift_and_escape_are_refused(fixture: _Fixture, mode: str) -> None:
    record = fixture.recorded()
    path = review.write_notebook_human_review(fixture.root / "review.json", record)
    proof = fixture.root / "proof.md"
    if mode == "changed":
        proof.write_bytes(proof.read_bytes() + b"changed")
    elif mode == "missing":
        proof.unlink()
    else:
        with pytest.raises(ValueError, match="escapes project_root"):
            fixture.recorded(evidence_path="../outside.md")
        with pytest.raises(ValueError, match="project-relative"):
            fixture.recorded(evidence_path=str(proof))
        return
    with pytest.raises(ValueError, match=r"evidence file changed|Cannot read bound file"):
        review.load_notebook_human_review(path, project_root=fixture.root)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "old"),
        ("baseline_artifact_sha256", "bad"),
        ("fixture_author_ids", []),
        ("fixture_author_ids", ["author", " AUTHOR "]),
        ("fixture_author_ids", {}),
        ("fixture_author_ids", [""]),
        ("decision", "other"),
        ("reviewer_kind", "robot"),
        ("independent_human_review", 1),
        ("reviewer_id", " "),
        ("review_date", "20261012"),
        ("review_date", "2026-99-01"),
        ("reviewed_revision", "abc"),
        ("checks", []),
        ("checks", [{"section": "a", "completed": True, "notes": ""}]),
        ("checks", [{"section": "a", "completed": False, "notes": 1}]),
        ("checks", [{"section": "a", "completed": 1, "notes": "test"}]),
        ("checks", [{"section": "a", "completed": False, "notes": "", "extra": True}]),
        ("evidence_file", {"role": "bad", "path": "proof.md", "sha256": "0" * 64, "size_bytes": 1}),
        (
            "evidence_file",
            {"role": "human_review_evidence", "path": "proof.md", "sha256": "bad", "size_bytes": 1},
        ),
        (
            "evidence_file",
            {
                "role": "human_review_evidence",
                "path": "proof.md",
                "sha256": "0" * 64,
                "size_bytes": 0,
            },
        ),
    ],
)
def test_strict_review_decoding(fixture: _Fixture, field: str, value: Any) -> None:
    payload = review.notebook_human_review_to_dict(fixture.pending())
    payload[field] = value
    _save_payload(fixture.root / "bad.json", payload)
    with pytest.raises(
        ValueError,
        match=r"version|SHA256|identities|array|empty|unsupported|boolean|date|month|Git|inventory|notes|fields|relative",
    ):
        review.load_notebook_human_review(fixture.root / "bad.json", project_root=fixture.root)


def test_strict_decision_fields_and_corrupt_review_digest(fixture: _Fixture) -> None:
    with pytest.raises(ValueError, match="fields"):
        review.record_notebook_human_review(fixture.pending(), {}, project_root=fixture.root)
    record = replace(fixture.pending(), content_sha256="0" * 64)
    with pytest.raises(ValueError, match="integrity mismatch"):
        review.notebook_human_review_to_dict(record)


@pytest.mark.parametrize("raw", ['{"x":1,"x":2}', '{"x":NaN}', "[]", "{"])
def test_bad_json_is_rejected(fixture: _Fixture, raw: str) -> None:
    path = fixture.root / "bad.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match=r"duplicate|finite|object|Expecting"):
        review.load_notebook_human_review(path, project_root=fixture.root)


def test_read_and_write_bounds_and_regular_files(fixture: _Fixture) -> None:
    pending = fixture.pending()
    path = review.write_notebook_human_review(fixture.root / "request.json", pending)
    assert (
        review.load_notebook_human_review(
            path, project_root=fixture.root, max_file_bytes=path.stat().st_size
        )
        == pending
    )
    for limit in (True, 0, 1):
        with pytest.raises(ValueError, match="max_file_bytes"):
            review.load_notebook_human_review(path, project_root=fixture.root, max_file_bytes=limit)
        with pytest.raises(ValueError, match="max_file_bytes"):
            review.write_notebook_human_review(
                fixture.root / f"limit-{limit}.json", pending, max_file_bytes=limit
            )
    with pytest.raises(ValueError, match="regular file"):
        review.load_notebook_human_review(fixture.root, project_root=fixture.root)


def test_wrapper_integrity_reference_and_proof_checks(fixture: _Fixture) -> None:
    wrapper = fixture.promote(fixture.recorded())
    with pytest.raises(ValueError, match="integrity mismatch"):
        review.reviewed_notebook_contract_to_dict(replace(wrapper, content_sha256="0" * 64))
    with pytest.raises(ValueError, match="operator_id must not be empty"):
        review._contract(wrapper.baseline, wrapper.review, " ")
    payload = review.reviewed_notebook_contract_to_dict(wrapper)
    payload["baseline_artifact_sha256"] = "0" * 64
    _save_payload(fixture.root / "wrong-wrapper.json", payload)
    with pytest.raises(ValueError, match="reference or content mismatch"):
        review.load_reviewed_notebook_contract(
            fixture.root / "wrong-wrapper.json",
            fixture.baseline_path,
            fixture.binding,
            fixture.capture,
            project_root=fixture.root,
        )
    path = review.write_reviewed_notebook_contract(fixture.root / "valid-wrapper.json", wrapper)
    (fixture.root / "proof.md").write_text("Changed synthetic proof.", encoding="utf-8")
    with pytest.raises(ValueError, match="evidence file changed"):
        review.load_reviewed_notebook_contract(
            path, fixture.baseline_path, fixture.binding, fixture.capture, project_root=fixture.root
        )


def _campaign_controls(**kwargs: Any) -> NotebookOllamaControls:
    model = "synthetic-campaign-model:test-only"
    payloads = {
        "version_before": {"version": "synthetic-server"},
        "version_after": {"version": "synthetic-server"},
        "tags_before": {"models": [{"name": model, "digest": "1" * 64}]},
        "tags_after": {"models": [{"name": model, "digest": "1" * 64}]},
        "show": {"model_info": {"general.architecture": "test", "test.context_length": 8192}},
    }
    return create_notebook_ollama_controls(
        model,
        tuple(
            NotebookOllamaResponse(role, json.dumps(payloads[role]))
            for role in ("version_before", "tags_before", "show", "version_after", "tags_after")
        ),
        requested=kwargs.pop(
            "requested", NotebookOllamaSettings(seed=7, num_ctx=4096, num_predict=1024)
        ),
        **kwargs,
    )


@pytest.fixture
def campaign_inputs(fixture: _Fixture) -> NotebookCampaignInputs:
    wrapper = fixture.promote(fixture.recorded())
    path = review.write_reviewed_notebook_contract(fixture.root / "reviewed.json", wrapper)
    return NotebookCampaignInputs(
        fixture.binding, path, fixture.baseline_path, fixture.capture, fixture.root
    )


def test_campaign_freezes_exact_requests_without_inference(
    campaign_inputs: NotebookCampaignInputs, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("campaign preparation must not execute code or query any service")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("notebook_to_kedro.evaluation.notebook_ollama._fetch_metadata", forbidden)
    monkeypatch.setattr("notebook_to_kedro.evaluation.notebook_execution._start_worker", forbidden)
    controls = _campaign_controls()
    prepared = prepare_notebook_campaign(campaign_inputs, controls)
    root = create_notebook_campaign(
        Path(campaign_inputs.project_root) / "campaign", campaign_inputs, controls
    )
    inspected = load_notebook_campaign(root, campaign_inputs, controls)
    assert inspected.campaign == prepared
    assert prepared.pipeline_attempt_budget == 1
    assert prepared.source_binding_sha256 == campaign_inputs.binding.content_sha256
    assert prepared.ollama_controls_sha256 == controls.content_sha256
    request = prepared.requests[0]
    body = json.loads(request.chat_body_json)
    assert body["model"] == controls.model_name
    assert body["options"] == {"temperature": 0.0, "seed": 7, "num_ctx": 4096, "num_predict": 1024}
    assert body["messages"] == [
        {"role": "user", "content": render_node_body_prompt(campaign_inputs.binding.requests[0])}
    ]
    assert body["format"]["type"] == "object"
    assert body["think"] is body["stream"] is False
    assert request.chat_body_sha256 == hashlib.sha256(request.chat_body_json.encode()).hexdigest()
    summary = notebook_campaign_summary(inspected)
    assert summary["planned_requests"] == 1
    assert summary["reserved_requests"] == summary["published_outcomes"] == 0
    assert summary["slots"] == [
        {"request_id": request.request_id, "task_id": request.task_id, "status": "not_requested"}
    ]
    assert summary["missing_request_ids"] == [request.request_id]
    assert summary["unfinished_request_ids"] == []
    assert not summary["complete_inventory"]
    assert (
        json.loads((Path(campaign_inputs.project_root) / "contract.json").read_text())["review"][
            "status"
        ]
        == "pending"
    )
    with pytest.raises(FileExistsError):
        create_notebook_campaign(root, campaign_inputs, controls)


@pytest.mark.parametrize("mode", ["response", "error", "interrupted", "publication_failure"])
def test_campaign_retains_every_reserved_outcome(
    campaign_inputs: NotebookCampaignInputs, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    controls = _campaign_controls()
    root = create_notebook_campaign(
        Path(campaign_inputs.project_root) / "campaign", campaign_inputs, controls
    )
    request = campaign_inputs.binding.requests[0]
    record = NotebookBodyRecord(request.request_id, raw_response="not even valid JSON")
    with pytest.raises(ValueError, match="reservation"):
        record_notebook_campaign_response(root, campaign_inputs, controls, record)
    reserve_notebook_campaign_request(root, campaign_inputs, controls, request.request_id)
    with pytest.raises(BehavioralBenchmarkArtifactError, match="already exists"):
        reserve_notebook_campaign_request(root, campaign_inputs, controls, request.request_id)
    if mode == "error":
        record = NotebookBodyRecord(
            request.request_id, provider_error=("synthetic_timeout", "test")
        )
    if mode == "publication_failure":

        def failed_write(*_args: Any, **_kwargs: Any) -> None:
            raise OSError("synthetic disk failure")

        with monkeypatch.context() as patch:
            patch.setattr("notebook_to_kedro.evaluation.notebook_capture._write", failed_write)
            with pytest.raises(OSError, match="synthetic disk"):
                record_notebook_campaign_response(root, campaign_inputs, controls, record)
    elif mode != "interrupted":
        # A fake provider result is persisted without schema/static validation or replacement.
        record_notebook_campaign_response(root, campaign_inputs, controls, record)
        with pytest.raises(BehavioralBenchmarkArtifactError, match="already exists"):
            record_notebook_campaign_response(root, campaign_inputs, controls, record)
    evidence = load_notebook_campaign(root, campaign_inputs, controls)
    summary = notebook_campaign_summary(evidence)
    unfinished = mode in ("interrupted", "publication_failure")
    assert summary["reserved_requests"] == 1
    assert summary["published_outcomes"] == (0 if unfinished else 1)
    assert summary["complete_inventory"] is not unfinished
    assert summary["unfinished_request_ids"] == ([request.request_id] if unfinished else [])
    slots = cast("list[dict[str, str]]", summary["slots"])
    assert slots[0]["status"] == (
        "unfinished" if unfinished else "provider_error" if mode == "error" else "raw_response"
    )
    assert evidence.capture.records == (() if unfinished else (record,))


@pytest.mark.parametrize("field", ["num_ctx", "num_predict"])
def test_campaign_requires_explicit_generation_budgets(
    campaign_inputs: NotebookCampaignInputs, field: str
) -> None:
    controls = _campaign_controls(
        requested=NotebookOllamaSettings(
            num_ctx=None if field == "num_ctx" else 4096,
            num_predict=None if field == "num_predict" else 1024,
        )
    )
    with pytest.raises(ValueError, match="explicit num_ctx and num_predict"):
        prepare_notebook_campaign(campaign_inputs, controls)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_timeout_seconds", True),
        ("provider_timeout_seconds", 0),
        ("provider_timeout_seconds", float("inf")),
        ("provider_timeout_seconds", float("nan")),
        ("provider_timeout_seconds", "120"),
        ("max_request_bytes", False),
        ("max_request_bytes", 0),
        ("max_request_bytes", 1),
        ("max_response_bytes", 0),
        ("max_capture_file_bytes", 16_777_217),
        ("max_capture_file_bytes", 1),
        ("max_file_bytes", True),
        ("max_file_bytes", 1),
    ],
)
def test_campaign_rejects_invalid_budgets_before_creating_directory(
    campaign_inputs: NotebookCampaignInputs, field: str, value: Any
) -> None:
    path = Path(campaign_inputs.project_root) / "invalid-campaign"
    with pytest.raises(ValueError, match=r"number|finite|positive|max_|hard limit"):
        create_notebook_campaign(path, campaign_inputs, _campaign_controls(), **{field: value})
    assert not path.exists()


@pytest.mark.parametrize(
    "target", ["proof.md", "reference.ipynb", "baseline.json", "reviewed.json"]
)
def test_campaign_rechecks_external_evidence_before_reservation(
    campaign_inputs: NotebookCampaignInputs, target: str
) -> None:
    controls = _campaign_controls()
    root = create_notebook_campaign(
        Path(campaign_inputs.project_root) / "campaign", campaign_inputs, controls
    )
    file = Path(campaign_inputs.project_root) / target
    file.write_bytes(file.read_bytes() + b"changed")
    with pytest.raises(ValueError, match=r"changed|Extra data|source hash"):
        reserve_notebook_campaign_request(
            root, campaign_inputs, controls, campaign_inputs.binding.requests[0].request_id
        )
    assert not list((root / "capture" / "attempts").iterdir())


def test_campaign_refuses_pending_review_and_changed_model_controls(
    fixture: _Fixture, campaign_inputs: NotebookCampaignInputs
) -> None:
    controls = _campaign_controls()
    root = create_notebook_campaign(fixture.root / "campaign", campaign_inputs, controls)
    changed = _campaign_controls(requested=NotebookOllamaSettings(num_ctx=4096, num_predict=512))
    with pytest.raises(ValueError, match="reconstructed evidence"):
        load_notebook_campaign(root, campaign_inputs, changed)
    data = json.loads(Path(campaign_inputs.reviewed_contract_path).read_text())
    data["review"] = review.notebook_human_review_to_dict(fixture.pending())
    Path(campaign_inputs.reviewed_contract_path).write_text(json.dumps(review._seal(data)))
    with pytest.raises(ValueError, match="approved independent human"):
        load_notebook_campaign(root, campaign_inputs, controls)


@pytest.mark.parametrize(
    "field",
    ["schema_version", "content_sha256", "ollama_controls_sha256", "requests", "extra"],
)
def test_campaign_rejects_rehashed_tampering(
    campaign_inputs: NotebookCampaignInputs, field: str
) -> None:
    controls = _campaign_controls()
    root = create_notebook_campaign(
        Path(campaign_inputs.project_root) / "campaign", campaign_inputs, controls
    )
    path = root / "manifest.json"
    data = json.loads(path.read_text())
    data[field] = [] if field == "requests" else "changed"
    data = review._seal(data) if field != "content_sha256" else data
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="reconstructed evidence"):
        load_notebook_campaign(root, campaign_inputs, controls)


@pytest.mark.parametrize(
    "mode", ["layout", "escape", "manifest_size", "capture_controls", "unknown"]
)
def test_campaign_inventory_guards(
    campaign_inputs: NotebookCampaignInputs, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    controls = _campaign_controls()
    root = create_notebook_campaign(
        Path(campaign_inputs.project_root) / "campaign", campaign_inputs, controls
    )
    if mode == "layout":
        (root / "unexpected").touch()
    elif mode == "escape":
        original = Path.resolve
        monkeypatch.setattr(
            Path,
            "resolve",
            lambda self: root.parent if self == root / "capture" else original(self),
        )
    elif mode == "manifest_size":
        with pytest.raises(ValueError, match="max_file_bytes"):
            load_notebook_campaign(root, campaign_inputs, controls, max_file_bytes=1)
        return
    elif mode == "capture_controls":
        path = root / "capture" / "manifest.json"
        data = json.loads(path.read_text())
        data["model_name"] = "wrong-model"
        path.write_text(json.dumps(data))
    else:
        with pytest.raises(ValueError, match="unknown"):
            reserve_notebook_campaign_request(root, campaign_inputs, controls, "unknown")
        return
    with pytest.raises(ValueError, match=r"layout|contained|controls mismatch"):
        load_notebook_campaign(root, campaign_inputs, controls)


def test_campaign_fake_provider_reference_flow_preserves_raw_before_static_validation(
    campaign_inputs: NotebookCampaignInputs,
) -> None:
    controls = _campaign_controls()
    root = create_notebook_campaign(
        Path(campaign_inputs.project_root) / "campaign", campaign_inputs, controls
    )
    planned = load_notebook_campaign(root, campaign_inputs, controls).campaign.requests
    calls = []
    sources = {
        item.chat_body_json: source
        for item, source in zip(planned, campaign_inputs.binding.requests, strict=True)
    }

    def fake_provider(body_json: str) -> str:
        inspected = load_notebook_campaign(root, campaign_inputs, controls)
        source_request = sources[body_json]
        assert source_request.request_id in inspected.capture.unfinished_request_ids
        calls.append(source_request.request_id)
        return NodeBodyResponse(
            "1.0", source_request.request_id, source_request.task_id, source_request.raw_source
        ).to_json()

    for planned_request in planned:
        reserve_notebook_campaign_request(
            root, campaign_inputs, controls, planned_request.request_id
        )

        raw = fake_provider(planned_request.chat_body_json)
        record_notebook_campaign_response(
            root, campaign_inputs, controls, NotebookBodyRecord(planned_request.request_id, raw)
        )
    evidence = load_notebook_campaign(root, campaign_inputs, controls)
    assert calls == [request.request_id for request in planned]
    assert notebook_campaign_summary(evidence)["complete_inventory"] is True
    replayed = replay_notebook_body_capture(
        root / "capture", campaign_inputs.binding, project_root=campaign_inputs.project_root
    )
    assert replayed.batch.accepted_count == replayed.batch.planned_count == len(planned)
    assert replayed.batch.static_ready


@pytest.mark.parametrize("mode", ["unknown", "drift", "insufficient"])
def test_campaign_model_identity_gate_precedes_publication(
    campaign_inputs: NotebookCampaignInputs, mode: str
) -> None:
    controls = _campaign_controls()
    records = list(controls.responses)
    index = 1 if mode == "unknown" else 3
    data = json.loads(records[index].raw_response)
    if mode == "unknown":
        data["models"] = []
    elif mode == "drift":
        data["version"] = "changed"
    if mode != "insufficient":
        records[index] = replace(records[index], raw_response=json.dumps(data))
    controls = create_notebook_ollama_controls(
        controls.model_name,
        records,
        requested=replace(controls.requested, num_ctx=16384)
        if mode == "insufficient"
        else controls.requested,
    )
    path = Path(campaign_inputs.project_root) / "invalid-model"
    with pytest.raises(ValueError, match=r"known versions|changed|sufficient"):
        create_notebook_campaign(path, campaign_inputs, controls)
    assert not path.exists()


@pytest.mark.parametrize(
    "field", ["options", "messages", "stream", "format", "source_request_sha256"]
)
def test_campaign_reconstructs_tampered_requests_even_with_new_hashes(
    campaign_inputs: NotebookCampaignInputs, field: str
) -> None:
    controls = _campaign_controls()
    root = create_notebook_campaign(
        Path(campaign_inputs.project_root) / "campaign", campaign_inputs, controls
    )
    path = root / "manifest.json"
    data = json.loads(path.read_text())
    request = data["requests"][0]
    if field == "source_request_sha256":
        request[field] = "0" * 64
    else:
        body = json.loads(request["chat_body_json"])
        body[field] = {"temperature": 1} if field == "options" else True
        request["chat_body_json"] = json.dumps(body)
        request["chat_body_sha256"] = hashlib.sha256(request["chat_body_json"].encode()).hexdigest()
    path.write_text(json.dumps(review._seal(data)))
    with pytest.raises(ValueError, match="reconstructed evidence"):
        load_notebook_campaign(root, campaign_inputs, controls)

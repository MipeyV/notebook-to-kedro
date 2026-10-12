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
    NotebookObservation,
    NotebookPipelineArtifact,
    NotebookPipelineRun,
    NotebookSourceBinding,
    ScalarBehaviorValue,
    collect_notebook_runtime_identity,
    create_notebook_body_capture,
    create_notebook_pipeline_artifact,
    create_notebook_source_binding,
    load_notebook_body_capture,
    record_notebook_body_response,
    replay_notebook_body_capture,
    reserve_notebook_body_request,
    write_notebook_pipeline_artifact,
)
from notebook_to_kedro.evaluation import notebook_review as review
from notebook_to_kedro.evaluation.behavioral_artifacts import write_json_exclusive
from notebook_to_kedro.evaluation.behavioral_execution import _result_from_worker
from notebook_to_kedro.evaluation.notebook_execution import NOTEBOOK_PIPELINE_EXECUTION_VERSION
from notebook_to_kedro.exceptions import BehavioralBenchmarkArtifactError
from notebook_to_kedro.generation.code import NodeBodyResponse

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

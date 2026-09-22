"""Immutable contracts for versioned planning evaluation cases."""

from __future__ import annotations

from dataclasses import dataclass
from string import hexdigits

PLANNING_CASE_SCHEMA_VERSION = "1.0"
SHA256_HEX_LENGTH = 64
TaskBoundary = tuple[tuple[str, ...], tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class ExpectedTask:
    """Human-reviewed task structure expected for one source fragment."""

    id: str
    expected_pipeline_id: str
    source_cell_ids: tuple[str, ...]
    statement_ids: tuple[str, ...]
    raw_source: str
    expected_node_name: str
    expected_inputs: tuple[str, ...]
    expected_outputs: tuple[str, ...]
    expected_parameters: tuple[str, ...] = ()
    expected_diagnostic_codes: tuple[str, ...] = ()

    @property
    def boundary(self) -> TaskBoundary:
        """Return the stable source boundary used to match predicted tasks."""
        return self.source_cell_ids, self.statement_ids

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "task id")
        _require_non_empty(self.expected_pipeline_id, "expected pipeline id")
        _require_non_empty(self.raw_source, "raw source")
        _require_non_empty(self.expected_node_name, "expected node name")
        if not self.source_cell_ids:
            msg = "expected task must reference at least one source cell"
            raise ValueError(msg)
        if not self.statement_ids:
            msg = "expected task must reference at least one statement"
            raise ValueError(msg)
        _require_unique(self.source_cell_ids, "source cell IDs")
        _require_unique(self.statement_ids, "statement IDs")
        _require_unique(self.expected_inputs, "expected inputs")
        _require_unique(self.expected_outputs, "expected outputs")
        _require_unique(self.expected_parameters, "expected parameters")
        _require_unique(self.expected_diagnostic_codes, "expected diagnostic codes")


@dataclass(frozen=True, slots=True)
class PlanningCase:
    """One reviewed notebook-to-plan evaluation example."""

    schema_version: str
    case_id: str
    notebook_path: str
    source_sha256: str
    review_status: str
    tasks: tuple[ExpectedTask, ...]
    expected_catalog_datasets: tuple[str, ...] = ()
    expected_parameter_names: tuple[str, ...] = ()
    expected_blocking_diagnostic_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != PLANNING_CASE_SCHEMA_VERSION:
            msg = f"unsupported planning case schema version: {self.schema_version!r}"
            raise ValueError(msg)
        _require_non_empty(self.case_id, "case id")
        _require_non_empty(self.notebook_path, "notebook path")
        if len(self.source_sha256) != SHA256_HEX_LENGTH or any(
            character not in hexdigits for character in self.source_sha256
        ):
            msg = "source_sha256 must be a 64-character hexadecimal digest"
            raise ValueError(msg)
        if self.review_status != "approved":
            msg = "planning evaluation cases must be explicitly approved"
            raise ValueError(msg)
        if not self.tasks:
            msg = "planning evaluation case must contain at least one expected task"
            raise ValueError(msg)
        _require_unique(tuple(task.id for task in self.tasks), "task IDs")
        _require_unique(tuple(task.boundary for task in self.tasks), "task boundaries")
        _require_unique(self.expected_catalog_datasets, "expected catalog datasets")
        _require_unique(self.expected_parameter_names, "expected parameter names")
        _require_unique(
            self.expected_blocking_diagnostic_codes,
            "expected blocking diagnostic codes",
        )


@dataclass(frozen=True, slots=True)
class PlanningEvaluation:
    """Dimension-level comparison between a reviewed case and a proposed plan."""

    case_id: str
    source_identity_match: bool
    expected_task_count: int
    predicted_task_count: int
    matched_task_count: int
    boundary_precision: float
    boundary_recall: float
    task_id_accuracy: float
    node_name_accuracy: float
    raw_source_accuracy: float
    input_accuracy: float
    output_accuracy: float
    parameter_accuracy: float
    diagnostic_accuracy: float
    pipeline_accuracy: float
    catalog_exact_match: bool
    parameter_names_exact_match: bool
    blocking_diagnostics_exact_match: bool
    exact_match: bool


def _require_non_empty(value: str, label: str) -> None:
    if not value:
        msg = f"{label} must not be empty"
        raise ValueError(msg)


def _require_unique(values: tuple[object, ...], label: str) -> None:
    if len(values) != len(set(values)):
        msg = f"{label} must be unique"
        raise ValueError(msg)

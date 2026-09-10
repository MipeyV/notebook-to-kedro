"""Immutable conversion planning contracts."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TaskCandidate:
    """Proposed Kedro-oriented task boundary derived from source facts."""

    id: str
    name: str
    source_cell_ids: tuple[str, ...]
    statement_ids: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    source: str
    diagnostic_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConversionPlan:
    """Deterministic semantic plan proposed from notebook facts."""

    schema_version: str
    planner_version: str
    notebook_path: str
    task_candidates: tuple[TaskCandidate, ...]
    imports: tuple[str, ...] = ()
    blocking_diagnostic_codes: tuple[str, ...] = ()

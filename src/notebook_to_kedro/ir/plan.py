"""Immutable conversion planning contracts."""

from dataclasses import dataclass

from notebook_to_kedro.ir.facts import JsonPrimitive


@dataclass(frozen=True, slots=True)
class CatalogDataset:
    """Dataset proposed for a generated Kedro catalog."""

    name: str
    type: str
    filepath: str
    source_filepath: str | None = None


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
    parameters: tuple[str, ...] = ()
    diagnostic_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ParameterValue:
    """Parameter proposed for generated Kedro configuration."""

    name: str
    value: JsonPrimitive
    function_argument: str
    source_cell_id: str


@dataclass(frozen=True, slots=True)
class ConversionPlan:
    """Deterministic semantic plan proposed from notebook facts."""

    schema_version: str
    planner_version: str
    notebook_path: str
    task_candidates: tuple[TaskCandidate, ...]
    imports: tuple[str, ...] = ()
    catalog_datasets: tuple[CatalogDataset, ...] = ()
    parameters: tuple[ParameterValue, ...] = ()
    blocking_diagnostic_codes: tuple[str, ...] = ()

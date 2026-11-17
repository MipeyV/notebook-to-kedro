"""Local configuration and concrete deterministic engine operations."""

from notebook_to_kedro.operations.configuration import (
    LocalProjectConfiguration,
    load_local_project_configuration,
)
from notebook_to_kedro.operations.contracts import (
    GenerateRequest,
    GenerationResult,
    InspectionResult,
    InspectRequest,
    PlanningResult,
    PlanRequest,
)
from notebook_to_kedro.operations.measurements import (
    load_effort_declaration,
    measure_local_operation,
    summarize_conversion_measurements,
)
from notebook_to_kedro.operations.service import (
    generate_project,
    inspect_project,
    plan_project,
    run_local_operation,
)

__all__ = [
    "GenerateRequest",
    "GenerationResult",
    "InspectRequest",
    "InspectionResult",
    "LocalProjectConfiguration",
    "PlanRequest",
    "PlanningResult",
    "generate_project",
    "inspect_project",
    "load_effort_declaration",
    "load_local_project_configuration",
    "measure_local_operation",
    "plan_project",
    "run_local_operation",
    "summarize_conversion_measurements",
]

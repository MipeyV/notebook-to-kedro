"""Explicit construction of supported semantic planners."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from notebook_to_kedro.exceptions import PlannerConfigurationError
from notebook_to_kedro.semantic.hybrid import HybridSemanticPlanner
from notebook_to_kedro.semantic.ollama import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    OllamaSemanticPlanningProvider,
)
from notebook_to_kedro.semantic.planner import DeterministicSemanticPlanner

if TYPE_CHECKING:
    from notebook_to_kedro.semantic.protocols import SemanticPlanner


class PlannerMode(StrEnum):
    """Planner implementations available through the public configuration API."""

    DETERMINISTIC = "deterministic"
    HYBRID = "hybrid"


def create_semantic_planner(
    mode: PlannerMode | str = PlannerMode.DETERMINISTIC,
    *,
    ollama_model: str | None = None,
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL,
    ollama_timeout_seconds: float = DEFAULT_OLLAMA_TIMEOUT_SECONDS,
) -> SemanticPlanner:
    """Create a supported planner from explicit local-provider settings."""
    try:
        selected_mode = PlannerMode(mode)
    except ValueError as error:
        choices = ", ".join(item.value for item in PlannerMode)
        raise PlannerConfigurationError(
            f"Unknown planner mode {mode!r}; expected one of: {choices}"
        ) from error

    if selected_mode is PlannerMode.DETERMINISTIC:
        if _has_ollama_configuration(
            model=ollama_model,
            base_url=ollama_base_url,
            timeout_seconds=ollama_timeout_seconds,
        ):
            raise PlannerConfigurationError("Ollama settings require planner mode 'hybrid'")
        return DeterministicSemanticPlanner()

    if not ollama_model:
        raise PlannerConfigurationError(
            "Hybrid planner mode requires a downloaded local model via ollama_model"
        )
    try:
        provider = OllamaSemanticPlanningProvider(
            model_name=ollama_model,
            base_url=ollama_base_url,
            timeout_seconds=ollama_timeout_seconds,
        )
    except ValueError as error:
        raise PlannerConfigurationError(f"Invalid Ollama configuration: {error}") from error
    return HybridSemanticPlanner(provider)


def _has_ollama_configuration(
    *,
    model: str | None,
    base_url: str,
    timeout_seconds: float,
) -> bool:
    return (
        model is not None
        or base_url != DEFAULT_OLLAMA_BASE_URL
        or timeout_seconds != DEFAULT_OLLAMA_TIMEOUT_SECONDS
    )


__all__ = ["PlannerMode", "create_semantic_planner"]

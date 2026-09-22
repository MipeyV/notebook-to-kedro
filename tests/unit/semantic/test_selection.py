"""Unit tests for explicit semantic planner selection."""

import pytest

from notebook_to_kedro.exceptions import PlannerConfigurationError
from notebook_to_kedro.semantic import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    DeterministicSemanticPlanner,
    HybridSemanticPlanner,
    OllamaSemanticPlanningProvider,
    PlannerMode,
    create_semantic_planner,
)


def test_create_semantic_planner_defaults_to_deterministic() -> None:
    planner = create_semantic_planner()

    assert isinstance(planner, DeterministicSemanticPlanner)


def test_create_semantic_planner_builds_local_hybrid_planner() -> None:
    planner = create_semantic_planner(
        PlannerMode.HYBRID,
        ollama_model="qwen2.5-coder:7b",
        ollama_base_url="http://127.0.0.1:11435",
        ollama_timeout_seconds=45,
    )

    assert isinstance(planner, HybridSemanticPlanner)
    assert isinstance(planner.provider, OllamaSemanticPlanningProvider)
    assert planner.provider.model_name == "qwen2.5-coder:7b"
    assert planner.provider.base_url == "http://127.0.0.1:11435"
    assert planner.provider.timeout_seconds == 45


def test_create_semantic_planner_rejects_unknown_mode() -> None:
    with pytest.raises(PlannerConfigurationError, match="Unknown planner mode 'remote'"):
        create_semantic_planner("remote")


def test_create_semantic_planner_requires_hybrid_model() -> None:
    with pytest.raises(
        PlannerConfigurationError,
        match="requires a downloaded local model via ollama_model",
    ):
        create_semantic_planner(PlannerMode.HYBRID)


@pytest.mark.parametrize(
    ("options", "expected_message"),
    [
        ({"ollama_model": "local-model"}, "Ollama settings require"),
        ({"ollama_base_url": "http://localhost:11435"}, "Ollama settings require"),
        ({"ollama_timeout_seconds": 10}, "Ollama settings require"),
    ],
)
def test_deterministic_planner_rejects_ollama_settings(
    options: dict[str, str | float], expected_message: str
) -> None:
    with pytest.raises(PlannerConfigurationError, match=expected_message):
        create_semantic_planner(PlannerMode.DETERMINISTIC, **options)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("options", "detail"),
    [
        ({"ollama_base_url": "https://localhost:11434"}, "local Ollama HTTP server"),
        ({"ollama_timeout_seconds": 0}, "positive finite number"),
    ],
)
def test_hybrid_planner_wraps_invalid_provider_configuration(
    options: dict[str, str | float], detail: str
) -> None:
    with pytest.raises(PlannerConfigurationError, match=detail):
        create_semantic_planner(
            PlannerMode.HYBRID,
            ollama_model="local-model",
            **options,  # type: ignore[arg-type]
        )


def test_planner_defaults_match_ollama_provider_defaults() -> None:
    planner = create_semantic_planner(PlannerMode.HYBRID, ollama_model="local-model")

    assert isinstance(planner, HybridSemanticPlanner)
    provider = planner.provider
    assert isinstance(provider, OllamaSemanticPlanningProvider)
    assert provider.base_url == DEFAULT_OLLAMA_BASE_URL
    assert provider.timeout_seconds == DEFAULT_OLLAMA_TIMEOUT_SECONDS

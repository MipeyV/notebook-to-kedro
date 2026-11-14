"""Synthetic independent loaders with an explicit source-ordered join."""


def load_values(raw_values: list) -> list:
    """Keep the loaded observations object."""
    return raw_values


def load_specification(raw_specification: dict) -> dict:
    """Keep a specification distinct from candidate settings."""
    return raw_specification


def evaluate(observations: list, specification: dict, candidate: dict) -> dict:
    """Produce a JSON-compatible synthetic result from both loader results."""
    return {
        "score": observations[0] * specification["scale"] + specification["offset"],
        "candidate": candidate["name"],
        "phase": candidate["phase"],
    }


def workflow(raw_values: list, raw_specification: dict, candidate: dict) -> dict:
    """Execute both loaders in source order before consuming their results once."""
    observations = load_values(raw_values)
    specification = load_specification(raw_specification)
    total = evaluate(observations, specification, candidate)
    return total

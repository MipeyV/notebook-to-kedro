"""Synthetic candidate configuration; this is not a financial benchmark."""


def evaluate(values: float, candidate: dict) -> dict:
    """Apply explicitly supplied settings to one synthetic numeric value."""
    return {
        "score": values * candidate["scale"] + candidate["offset"],
        "candidate": candidate["name"],
        "phase": candidate["phase"],
        "seed": candidate["seed"],
        "enabled": candidate["enabled"],
        "note": candidate["note"],
    }


def workflow(values: float, candidate: dict) -> dict:
    """Pass a candidate mapping once at the orchestration boundary."""
    total = evaluate(values, candidate)
    return total

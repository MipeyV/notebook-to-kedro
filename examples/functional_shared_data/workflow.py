"""Preserve an explicitly shared buffer and the order of its mutations."""


def create_buffer(raw_values: list) -> dict:
    """Keep one buffer around the input values."""
    return {"values": raw_values, "events": []}


def read_left(buffer: dict, gain: float) -> dict:
    """Record the first consumer on the shared buffer."""
    buffer["events"].append("left")
    return {"score": sum(buffer["values"]) * gain, "buffer": buffer}


def read_right(buffer: dict, bias: float) -> dict:
    """Record the second consumer on the same buffer."""
    buffer["events"].append("right")
    return {"score": sum(buffer["values"]) + bias, "buffer": buffer}


def combine(left: dict, right: dict) -> dict:
    """Verify shared identity and source order before publishing scores."""
    assert left["buffer"] is right["buffer"], "Shared buffer identity changed"
    assert left["buffer"]["events"] == ["left", "right"], "Source call order changed"
    return {
        "left_score": left["score"],
        "right_score": right["score"],
        "events": left["buffer"]["events"],
    }


def workflow(raw_values: list, gain: float, bias: float) -> dict:
    """Call each helper once while preserving the shared reference."""
    buffer = create_buffer(raw_values)
    left = read_left(buffer, gain)
    right = read_right(buffer, bias)
    report = combine(left, right)
    return report

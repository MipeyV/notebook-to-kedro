"""Source-coordinate evidence shared by deterministic and model-assisted generation."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParameterReplacement:
    """Replace the complete source expression at a half-open character range."""

    parameter_name: str
    function_argument: str
    source_expression: str
    value_type: str
    start_offset: int
    end_offset: int

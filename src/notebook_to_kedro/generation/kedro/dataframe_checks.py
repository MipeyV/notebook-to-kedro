"""Compose optional DataFrame metadata checks without importing or repairing data."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from notebook_to_kedro.generation.kedro.generator import _PipelineEntry
    from notebook_to_kedro.generation.kedro.node_types import NotebookTypeContract

SCHEMA_CHECK_EXTENSION = '''

from typing import Any, cast

_FrameSpec = tuple[str, tuple[tuple[str, str], ...], bool]


def _check_frame(value: Any, spec: _FrameSpec, location: str) -> None:
    """Inspect column/dtype metadata without reordering, casting or reading row values."""
    dataset, columns, allow_extra = spec
    actual = tuple(value.columns)
    if any(not isinstance(name, str) for name in actual) or len(set(actual)) != len(actual):
        raise ValueError(f"{location} {dataset}: expected unique flat string columns")
    expected = tuple(name for name, _ in columns)
    observed = tuple(name for name in actual if name in expected) if allow_extra else actual
    if observed != expected:
        raise ValueError(f"{location} {dataset}: column order or extra-column policy mismatch")
    for name, dtype in columns:
        observed_dtype = str(value[name].dtype)
        if observed_dtype != dtype:
            raise ValueError(f"{location} {dataset} column {name!r}: expected dtype {dtype}")


def validate_frame_node(
    *, task_id: str, inputs: Mapping[str, _Spec], outputs: tuple[_Spec | None, ...],
    input_frames: Mapping[str, _FrameSpec], output_frames: tuple[_FrameSpec | None, ...]
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Prepare class and DataFrame metadata boundaries without running business code.

    Args:
        task_id: Source task identity for diagnostics.
        inputs: Declared argument classes.
        outputs: Declared return classes, in source order.
        input_frames: Declared DataFrame metadata by argument.
        output_frames: Declared DataFrame metadata by return slot.

    Returns:
        A decorator preserving source signatures, exceptions and return identity.
    """
    input_types = dict(inputs)
    frames_in = dict(input_frames)
    frames_out = tuple(output_frames)

    def decorate(function: Callable[_P, _R]) -> Callable[_P, _R]:
        """Compose with the unchanged class validator."""
        validated = validate_node(task_id=task_id, inputs=inputs, outputs=outputs)(function)
        call_signature = signature(validated)

        @wraps(validated)
        def checked(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            """Check frame metadata around the class-validated source call."""
            bound = call_signature.bind(*args, **kwargs)
            for argument, spec in frames_in.items():
                value = bound.arguments[argument]
                _check_type(value, input_types[argument], f"NTV001 {task_id} input")
                _check_frame(value, spec, f"NVS001 {task_id} input")
            result = validated(*args, **kwargs)
            for index, spec in enumerate(frames_out):
                if spec is not None:
                    value = (
                        result if len(frames_out) == 1
                        else cast(tuple[object, ...], result)[index]
                    )
                    _check_frame(value, spec, f"NVS002 {task_id} output")
            return result

        return checked

    return decorate
'''


def _frame_spec(dataset: str, contract: NotebookTypeContract) -> str:
    frame = dict(contract.dataframes).get(dataset)
    if frame is None:
        return "None"
    return repr((dataset, frame.columns, frame.allow_extra_columns))


def frame_decorator_arguments(entry: _PipelineEntry, contract: NotebookTypeContract) -> str:
    """Bind immutable schema literals to the same real dataset versions as class checks."""
    frames = dict(contract.dataframes)
    inputs = [
        f"{argument!r}: {_frame_spec(dataset, contract)}"
        for argument, dataset in entry.inputs.items()
        if dataset in frames
    ]
    outputs = [_frame_spec(dataset, contract) for dataset in entry.outputs]
    output_tuple = "(" + ", ".join(outputs) + (",)" if outputs else ")")
    return f"    input_frames={{{', '.join(inputs)}}}, output_frames={output_tuple},\n"

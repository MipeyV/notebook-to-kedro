"""Derive exact parameter evidence using the same source rules as V1 generation."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from notebook_to_kedro.generation.kedro import parameter_replacements
from notebook_to_kedro.ir import TaskCandidate

if TYPE_CHECKING:
    from notebook_to_kedro.generation.code.contracts import NodeCodeRequest
    from notebook_to_kedro.generation.parameters import ParameterReplacement

NODE_CODE_PARAMETER_EVIDENCE_VERSION = "1.0"


def build_parameter_evidence(request: NodeCodeRequest) -> tuple[ParameterReplacement, ...]:
    """Require one unambiguous literal expression per requested parameter, without execution."""
    task = TaskCandidate(
        id=request.task_id,
        name=request.node_name,
        source_cell_ids=request.source_cell_ids,
        statement_ids=request.statement_ids,
        inputs=request.inputs,
        outputs=request.outputs,
        source=request.raw_source,
        parameters=request.parameter_names,
    )
    arguments = dict(zip(request.parameter_names, request.parameter_arguments, strict=True))
    replacements = parameter_replacements(task)
    names = tuple(item.parameter_name for item in replacements)
    if len(names) != len(set(names)) or set(names) != set(arguments):
        raise ValueError("parameter evidence requires exactly one source expression per parameter")
    return tuple(
        replace(item, function_argument=arguments[item.parameter_name]) for item in replacements
    )

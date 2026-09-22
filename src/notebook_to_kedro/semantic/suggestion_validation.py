"""Cross-validation of semantic suggestions against deterministic V1 facts."""

from notebook_to_kedro.exceptions import SemanticPlanningResponseError
from notebook_to_kedro.semantic.contracts import (
    SemanticPlanningRequest,
    SemanticPlanningResponse,
)


def validate_semantic_planning_response(
    request: SemanticPlanningRequest, response: SemanticPlanningResponse
) -> None:
    """Reject suggestions that drop, invent, or misattribute deterministic facts."""
    errors: list[str] = []
    if response.request_id != request.request_id:
        errors.append("response request_id does not match the request")

    cells_by_id = {cell.id: cell for cell in request.facts.cells}
    statement_cells = {
        statement.id: cell.id for cell in request.facts.cells for statement in cell.statements
    }
    baseline_statement_ids = {
        statement_id
        for task in request.baseline_plan.task_candidates
        for statement_id in task.statement_ids
    }
    allowed_inputs = {
        name for task in request.baseline_plan.task_candidates for name in task.inputs
    }
    allowed_inputs.update(dataset.name for dataset in request.baseline_plan.catalog_datasets)
    allowed_outputs = {
        name for task in request.baseline_plan.task_candidates for name in task.outputs
    }
    parameters_by_name = {
        parameter.name: parameter for parameter in request.baseline_plan.parameters
    }

    assigned_statement_ids: list[str] = []
    for task in response.tasks:
        selected_cells = set(task.source_cell_ids)
        unknown_cells = selected_cells - cells_by_id.keys()
        errors.extend(
            f"task {task.node_name} references unknown cell: {cell_id}"
            for cell_id in sorted(unknown_cells)
        )

        known_task_statements = {
            statement_id for statement_id in task.statement_ids if statement_id in statement_cells
        }
        unknown_statements = set(task.statement_ids) - statement_cells.keys()
        errors.extend(
            f"task {task.node_name} references unknown statement: {statement_id}"
            for statement_id in sorted(unknown_statements)
        )
        errors.extend(
            f"task {task.node_name} statement {statement_id} is not in its source cells"
            for statement_id in sorted(known_task_statements)
            if statement_cells[statement_id] not in selected_cells
        )
        represented_cells = {
            statement_cells[statement_id] for statement_id in known_task_statements
        }
        errors.extend(
            f"task {task.node_name} source cell has no selected statement: {cell_id}"
            for cell_id in sorted(selected_cells - represented_cells - unknown_cells)
        )
        errors.extend(
            f"task {task.node_name} references unsupported input: {name}"
            for name in task.inputs
            if name not in allowed_inputs
        )
        errors.extend(
            f"task {task.node_name} references unsupported output: {name}"
            for name in task.outputs
            if name not in allowed_outputs
        )
        for parameter_name in task.parameter_names:
            parameter = parameters_by_name.get(parameter_name)
            if parameter is None:
                errors.append(
                    f"task {task.node_name} references unknown parameter: {parameter_name}"
                )
            elif parameter.source_cell_id not in selected_cells:
                errors.append(
                    f"task {task.node_name} parameter {parameter_name} does not belong to "
                    "its source cells"
                )
        assigned_statement_ids.extend(task.statement_ids)

    duplicate_statement_ids = {
        statement_id
        for index, statement_id in enumerate(assigned_statement_ids)
        if statement_id in assigned_statement_ids[:index]
    }
    errors.extend(
        f"statement is assigned to multiple tasks: {statement_id}"
        for statement_id in sorted(duplicate_statement_ids)
    )
    assigned_statement_set = set(assigned_statement_ids)
    errors.extend(
        f"baseline statement is missing from suggestions: {statement_id}"
        for statement_id in sorted(baseline_statement_ids - assigned_statement_set)
    )
    errors.extend(
        f"suggestion contains a non-baseline statement: {statement_id}"
        for statement_id in sorted(assigned_statement_set - baseline_statement_ids)
    )

    if errors:
        details = "\n".join(f"- {error}" for error in errors)
        message = f"Invalid semantic planning response:\n{details}"
        raise SemanticPlanningResponseError(message)

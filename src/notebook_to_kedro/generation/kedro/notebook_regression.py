"""Bind explicit procedural tests to the backend's actual dataset and node names."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from notebook_to_kedro.exceptions import WorkflowRegressionError
from notebook_to_kedro.generation.kedro.model_reload_template import MODEL_TESTS, MODEL_WORKER
from notebook_to_kedro.generation.kedro.notebook_test_template import TEST_MODULE

if TYPE_CHECKING:
    from collections.abc import Mapping

    from notebook_to_kedro.generation.kedro.generator import _PipelineEntry
    from notebook_to_kedro.generation.kedro.model_output import ModelOutputBinding
    from notebook_to_kedro.generation.kedro.notebook_regression_contract import (
        NotebookRegressionContract,
    )
    from notebook_to_kedro.ir import ConversionPlan


def _binding(
    plan: ConversionPlan, entries: tuple[_PipelineEntry, ...], names: Mapping[str, str]
) -> dict[str, Any]:
    return {
        "catalog": {
            dataset.name: {"type": dataset.type, "filepath": dataset.filepath}
            for dataset in plan.catalog_datasets
        },
        "produced": [output for entry in entries for output in entry.outputs],
        "final_outputs": list(entries[-1].outputs) if entries else [],
        "nodes": {
            entry.task.id: {
                "name": names[entry.task.id],
                "outputs": list(entry.task.outputs),
                "datasets": list(entry.outputs),
                "inputs": list(entry.inputs) + list(entry.parameters),
            }
            for entry in entries
        },
    }


def _validate_binding(
    cases: list[dict[str, Any]], binding: dict[str, Any], parameters: set[str], leaves: set[str]
) -> None:
    for case in cases:
        if set(case["inputs"]) != set(binding["catalog"]) or set(case["parameters"]) != parameters:
            raise WorkflowRegressionError("Scenario inputs/parameters must match the plan exactly")
        if "expected" in case and not set(case["expected"]) <= leaves:
            raise WorkflowRegressionError("Pipeline expectations must name generated leaf datasets")
        if "raises" in case and case["raises"]["node"] not in binding["nodes"]:
            raise WorkflowRegressionError("Pipeline exceptions must name a source task ID")
        for name, node in case.get("nodes", {}).items():
            if name not in binding["nodes"] or set(node["inputs"]) != set(
                binding["nodes"][name]["inputs"]
            ):
                raise WorkflowRegressionError(
                    "Node cases must match task IDs and wrapper arguments"
                )
            if "expected" in node and set(node["expected"]) != set(
                binding["nodes"][name]["outputs"]
            ):
                raise WorkflowRegressionError("Node expectations must cover every source output")


def render_notebook_regressions(  # noqa: PLR0913
    plan: ConversionPlan,
    contract: NotebookRegressionContract,
    entries: tuple[_PipelineEntry, ...],
    *,
    names: Mapping[str, str],
    ordering_inputs: Mapping[str, str],
    package_name: str,
    pipeline_name: str,
    source_sha256: str,
    model_output: ModelOutputBinding | None = None,
) -> dict[Path, str]:
    """Render only supplied oracles; absent cases remain explicit generation-time gaps."""
    binding = _binding(plan, entries, names)
    leaves = (
        set(binding["produced"])
        - {value for entry in entries for value in entry.inputs.values()}
        - set(ordering_inputs.values())
    )
    data = contract.to_dict()
    cases = data["scenarios"]
    model_checks = data.get("model_checks", [])
    if model_checks and model_output is None:
        raise WorkflowRegressionError("Model reload checks require an explicit model_output")
    _validate_binding(cases, binding, {parameter.name for parameter in plan.parameters}, leaves)
    observed = {output for case in cases for output in case.get("expected", {})}
    covered = {name for case in cases for name in case.get("nodes", {})}
    positive = {
        name for case in cases for name, node in case.get("nodes", {}).items() if "expected" in node
    }
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "execution_status": "not_run",
        "review_status": "not_authenticated",
        "contract_sha256": contract.sha256,
        "source_sha256": source_sha256,
        "pipeline_scenarios": len(cases),
        "pipeline_exception_scenarios": sum("raises" in case for case in cases),
        "node_scenarios": sum(len(case.get("nodes", {})) for case in cases),
        "node_exception_scenarios": sum(
            "raises" in node for case in cases for node in case.get("nodes", {}).values()
        ),
        "missing_pipeline_outputs": sorted(leaves - observed),
        "missing_node_expectations": sorted(set(binding["nodes"]) - covered),
        "missing_node_positive_expectations": sorted(set(binding["nodes"]) - positive),
        "limitations": "Explicit finite JSON/numeric/array/flat pandas observations only; "
        "no model serialization, scientific-quality or general equivalence proof.",
    }
    files = {
        Path("regression-coverage.json"): json.dumps(report, indent=2, sort_keys=True) + "\n",
        Path("TESTING.md"): (
            "# Supplied notebook regression tests\n\n"
            "Install this project with `python -m pip install -e '.[test]'`, then run "
            "`python -m pytest`. Running tests executes project code. "
            "Generation only validates and compiles files; it does not run tests.\n\n"
            "Expectations and SHA-pinned CSV fixtures are supplied explicitly. "
            "`regression-coverage.json` records missing observations, including nodes with "
            "only exception cases. It is not a runtime coverage or approval report. "
            "No tests are emitted when the explicit scenario list is empty.\n"
        ),
    }
    if model_checks:
        report.update(
            model_reload_checks=len(model_checks),
            model_reload_methods=sorted({check["method"] for check in model_checks}),
            model_reload_status="not_run",
        )
        report["limitations"] += (
            " Supplied reload probes check finite numeric predictions only, not full object "
            "state, scientific quality or deployment readiness."
        )
        files[Path("regression-coverage.json")] = (
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        files[Path("TESTING.md")] += (
            "\nModel reload tests train the declared positive scenario in an isolated test "
            "workspace, save the selected model, then reload it in a fresh Python process. "
            "Only supplied probes/prediction oracles are checked; generation runs none of them.\n"
        )
    if not cases:
        return files
    for name, text in contract.fixture_texts:
        digest = data["fixtures"][name]["sha256"]
        relative = f"regression_fixtures/{digest}.csv"
        data["fixtures"][name]["path"] = relative
        files[Path("tests") / relative] = text
    payload = {
        **binding,
        "contract": data,
        "package_name": package_name,
        "nodes_module": f"{package_name}.pipelines.{pipeline_name}.nodes",
    }
    module = TEST_MODULE
    if model_output is not None:
        payload["model_output"] = {
            "dataset": model_output.dataset,
            "configuration": model_output.catalog_config(),
        }
        # A model-only catalog still needs validation when there are no CSV inputs.
        module = module.replace(' if DATA[\n        "catalog"\n    ] else {}', "")
        module = module.replace(
            '    if config != DATA["catalog"]:\n',
            '    storage = DATA["model_output"]\n'
            '    if config.pop(storage["dataset"], None) != storage["configuration"]:\n'
            '        raise ValueError("Regression model catalog declaration changed")\n'
            '    if config != DATA["catalog"]:\n',
        )
    if model_checks:
        module = module.replace(
            "def _catalog(case, tmp_path, monkeypatch):",
            "def _catalog(case, tmp_path, monkeypatch, save_version=None):",
        ).replace(
            "catalog = DataCatalog.from_config(prepared)",
            "catalog = DataCatalog.from_config(prepared, save_version=save_version)",
        )
        module += MODEL_TESTS
        compile(MODEL_WORKER, "tests/_model_reload_worker.py", "exec", dont_inherit=True)
        files[Path("tests/_model_reload_worker.py")] = MODEL_WORKER
    files[Path("tests/regression_cases.json")] = (
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )
    compile(module, "tests/test_notebook_regressions.py", "exec", dont_inherit=True)
    files[Path("tests/test_notebook_regressions.py")] = module
    return files

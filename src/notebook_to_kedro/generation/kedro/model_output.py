"""Bind one explicitly selected notebook leaf to local, versioned pickle storage."""

from __future__ import annotations

import json
import keyword
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from notebook_to_kedro.exceptions import ProjectGenerationError

if TYPE_CHECKING:
    from notebook_to_kedro.generation.kedro.generator import _PipelineEntry

MODEL_FILEPATH = "data/06_models/model.pkl"


@dataclass(frozen=True, slots=True)
class ModelOutputBinding:
    """An operator declaration bound to a real leaf; not inferred model/type evidence."""

    symbol: str
    dataset: str
    task_id: str
    source_sha256: str

    def catalog_config(self) -> dict[str, str | bool]:
        """Use the stdlib backend and Kedro's ordinary append-version storage."""
        return {
            "type": "kedro_datasets.pickle.PickleDataset",
            "filepath": MODEL_FILEPATH,
            "backend": "pickle",
            "versioned": True,
        }

    def catalog_source(self) -> str:
        """Render a quoted YAML entry without importing a YAML or dataset library."""
        lines = [json.dumps(self.dataset) + ":"]
        lines.extend(
            f"  {key}: {json.dumps(value)}" for key, value in self.catalog_config().items()
        )
        return "\n".join(lines) + "\n"

    def files(self) -> dict[Path, str]:
        """Describe the declaration without claiming a saved/reloaded model exists."""
        manifest = {
            "schema_version": "1.0",
            "source_sha256": self.source_sha256,
            "source_symbol": self.symbol,
            "dataset": self.dataset,
            "source_task_id": self.task_id,
            "catalog": self.catalog_config(),
            "execution_status": "not_run",
            "runtime_type_status": "not_verified",
            "reload_validation_status": "not_run",
            "generated_regressions_validate_storage": False,
        }
        guide = (
            "# Explicit model output\n\n"
            f"The declared source symbol `{self.symbol}` is bound to leaf dataset "
            f"`{self.dataset}` with local versioned pickle storage at `{MODEL_FILEPATH}`. "
            "Run from the generated project root: `kedro run` executes project code and writes "
            "a new Kedro save version. Catalog paths follow the runtime working directory. "
            "Generation saves no model and verifies no runtime type or predictions.\n\n"
            "Load an explicitly selected version with `DataCatalog.from_config(..., "
            f"load_versions={{{self.dataset!r}: VERSION}}).load({self.dataset!r})`. "
            "Keep the compatible Python environment, importable model classes and library "
            "versions available. Other leaves such as a selected threshold, metrics or "
            "decision policy are not bundled automatically. This is not a portable model "
            "export or deployment contract.\n\n"
            "Only load self-produced, trusted pickle files: unpickling can execute code. "
            "Kedro owns version lookup/save behavior; no concurrent writer lock, transaction, "
            "partial-file cleanup or arbitrary-object serialization guarantee is added.\n\n"
            "If supplied regression tests are generated, they verify the exact catalog "
            "declaration but replace produced datasets with memory datasets in isolated "
            "test workspaces. They do not save/reload this model or infer an object oracle. "
            "Missing model expectations remain in `regression-coverage.json`. Validate reload "
            "behavior and predictions separately before relying on an artifact.\n"
        )
        return {
            Path("model-output.json"): json.dumps(manifest, sort_keys=True, indent=2) + "\n",
            Path("MODEL_OUTPUT.md"): guide,
        }


def bind_model_output(
    symbol: str,
    entries: tuple[_PipelineEntry, ...],
    source_sha256: str,
    ordering_inputs: tuple[str, ...] = (),
) -> ModelOutputBinding:
    """Select the latest source value only when no generated node consumes it."""
    if not isinstance(symbol, str) or not symbol.isidentifier() or keyword.iskeyword(symbol):
        raise ProjectGenerationError("model_output must be a Python source identifier")
    latest = {
        source: (dataset, entry.task.id)
        for entry in entries
        for source, dataset in zip(entry.task.outputs, entry.outputs, strict=True)
    }
    consumed = {dataset for entry in entries for dataset in entry.inputs.values()} | set(
        ordering_inputs
    )
    if symbol not in latest or latest[symbol][0] in consumed:
        raise ProjectGenerationError(
            "model_output must name the latest value of a generated leaf output"
        )
    dataset, task_id = latest[symbol]
    if dataset == "parameters":
        raise ProjectGenerationError(
            "model_output conflicts with Kedro's reserved parameters dataset"
        )
    return ModelOutputBinding(symbol, dataset, task_id, source_sha256)

"""Catalog inputs and their first in-memory rewrite need distinct graph identities."""

import importlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from kedro.config import OmegaConfigLoader
from kedro.io import DataCatalog, MemoryDataset
from kedro.runner import SequentialRunner

from notebook_to_kedro import (
    analyze_notebook_path,
    audit_conversion_source,
    generate_kedro_project,
    plan_notebook_path,
)


@pytest.mark.integration
def test_first_catalog_rewrite_executes_with_distinct_input_output_datasets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    csv = tmp_path / "source.csv"
    csv.write_text("value\n1\n2\n", encoding="utf-8")
    notebook = tmp_path / "source.ipynb"
    sources = (
        "import pandas as pd",
        'df = pd.read_csv("source.csv")',
        'df = df.assign(value=df["value"] * 2)',
        'total = int(df["value"].sum())\nassert total == 6',
    )
    notebook.write_text(
        json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {"language_info": {"name": "python"}},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": f"source-{index}",
                        "metadata": {},
                        "execution_count": None,
                        "outputs": [],
                        "source": source,
                    }
                    for index, source in enumerate(sources)
                ],
            }
        ),
        encoding="utf-8",
    )
    facts = analyze_notebook_path(notebook)
    plan = plan_notebook_path(notebook)
    assert audit_conversion_source(facts, plan).complete
    destination = tmp_path / "project"
    generate_kedro_project(plan, destination, package_name="catalog_versioned", source_facts=facts)
    monkeypatch.syspath_prepend(str(destination / "src"))
    monkeypatch.chdir(destination)
    module = cast("Any", importlib.import_module("catalog_versioned.pipeline_registry"))
    pipeline = module.register_pipelines()["__default__"]
    first = next(node for node in pipeline.nodes if node.name == "engineer_features")
    assert first.inputs == ["df"]
    assert first.outputs == ["df__engineer_features"]
    config = OmegaConfigLoader(conf_source=str(destination / "conf/base"))
    catalog = DataCatalog.from_config(config["catalog"])
    for name in pipeline.datasets() - {"df"}:
        catalog[name] = MemoryDataset()
    SequentialRunner().run(pipeline, catalog)
    assert catalog.load("total") == 6
    assert (destination / "data/01_raw/source.csv").read_bytes() == csv.read_bytes()

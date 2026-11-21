"""Author a tiny supplied-oracle reload example without executing its model."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from notebook_to_kedro.generation.writer import write_project


def _json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def build_files() -> dict[Path, str]:
    """Use hand-declared separable labels and endpoint probes, not captured predictions."""
    files = {
        Path("data/training.csv"): "x,y\n0.0,0\n1.0,0\n2.0,1\n3.0,1\n",
        Path("data/empty.csv"): "x,y\n",
        Path("data/probe.csv"): "x\n0.0\n3.0\n",
    }
    code = [
        "import pandas as pd\nfrom sklearn.tree import DecisionTreeClassifier\n\n"
        'df = pd.read_csv("data/training.csv")\nassert not df.empty\nX = df[["x"]]\ny = df["y"]',
        "model = DecisionTreeClassifier(random_state=42)\nmodel.fit(X, y)",
        "predictions = model.predict(X)\nfitted_model = model",
    ]
    files[Path("workflow.ipynb")] = (
        json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {"language_info": {"name": "python"}},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": f"stage-{i}",
                        "metadata": {},
                        "execution_count": None,
                        "outputs": [],
                        "source": source.splitlines(keepends=True),
                    }
                    for i, source in enumerate(code)
                ],
            },
            sort_keys=True,
            indent=1,
        )
        + "\n"
    )
    fixtures = {
        name: {
            "path": f"data/{name}.csv",
            "sha256": hashlib.sha256(files[Path(f"data/{name}.csv")].encode()).hexdigest(),
        }
        for name in ("training", "empty", "probe")
    }
    files[Path("regression.json")] = _json(
        {
            "schema_version": "1.1",
            "fixtures": fixtures,
            "scenarios": [
                {
                    "id": "baseline",
                    "inputs": {"df": "training"},
                    "parameters": {},
                    "expected": {
                        "predictions": {"kind": "array", "dtype": "int64", "data": [0, 0, 1, 1]}
                    },
                },
                {
                    "id": "empty",
                    "inputs": {"df": "empty"},
                    "parameters": {},
                    "raises": {"type": "AssertionError", "message": "", "node": "task-0000"},
                },
            ],
            "model_checks": [
                {
                    "id": "reload-labels",
                    "scenario": "baseline",
                    "method": "predict",
                    "input": {"kind": "csv", "fixture": "probe"},
                    "expected": {"kind": "array", "dtype": "int64", "data": [0, 1]},
                    "abs_tol": 0,
                    "rel_tol": 0,
                },
                {
                    "id": "reload-probabilities",
                    "scenario": "baseline",
                    "method": "predict_proba",
                    "input": {"kind": "csv", "fixture": "probe"},
                    "expected": {
                        "kind": "array",
                        "dtype": "float64",
                        "data": [[1.0, 0.0], [0.0, 1.0]],
                    },
                    "abs_tol": 1e-12,
                    "rel_tol": 0,
                },
            ],
        }
    )
    files[Path("project.json")] = _json(
        {
            "schema_version": "1.0",
            "project_root": ".",
            "source_kind": "notebook",
            "source": "workflow.ipynb",
            "package_name": "reloaded_tree",
            "regression_contract": "regression.json",
            "model_output": "fitted_model",
        }
    )
    return files


def main() -> None:
    """Publish static example assets to a new destination."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    paths = write_project(args.output, build_files())
    print(f"Wrote {len(paths)} supplied-oracle model test assets")  # noqa: T201


if __name__ == "__main__":
    main()

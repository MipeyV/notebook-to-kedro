"""Three hand-chosen observations and application-owned JSON/Parquet artifacts."""

import hashlib
import importlib.metadata
import json
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

TRACE = []


@dataclass
class BenchmarkResult:
    directory: Path
    metrics: dict
    metadata: dict


def load_market(path):
    TRACE.append("market")
    return json.loads(Path(path).read_text())


def load_protocol(path):
    TRACE.append("protocol")
    return json.loads(Path(path).read_text())


def run_benchmark(dataset, protocol, candidate):
    TRACE.append("benchmark")
    assert candidate["phase"] == "validation"
    output = Path(candidate["output"])
    output.mkdir(parents=True, exist_ok=False)
    (output / "protocol.json").write_text(json.dumps(protocol))
    # FAILURE_INJECTION
    origins = pd.date_range("2022-01-03", periods=3)
    table = pd.DataFrame(
        {
            "origin": origins,
            "target_start": origins + pd.Timedelta(days=1),
            "target_timestamp": origins + pd.Timedelta(days=1),
            "asset": "SYNTH",
            "horizon": 1,
            "target": "value",
            "actual": dataset["actual"],
            "predicted": [2.0, 2.0, 2.0],
        }
    )
    error = table.predicted.to_numpy() - table.actual.to_numpy()
    metrics = {"mae": float(np.mean(np.abs(error))), "rmse": float(np.sqrt(np.mean(error**2)))}
    metrics.update({f"{key}/h1/value": value for key, value in tuple(metrics.items())})
    prefix = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false"]
    commit = subprocess.run(
        [*prefix, "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    dirty = subprocess.run(
        [*prefix, "status", "--porcelain"], capture_output=True, text=True, check=False
    )
    package = Path(__file__).parent
    metadata = {
        "phase": "validation",
        "seed": candidate["seed"],
        "estimator_name": "naive",
        "benchmark_id": protocol["benchmark_id"],
        "benchmark_version": protocol["version"],
        "benchmark_fingerprint": hashlib.sha256(
            json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "dataset_fingerprint": protocol["dataset_fingerprint"],
        "evaluation_fingerprint": "synthetic-coordinates",
        "selected_features": protocol["feature_names"],
        "horizons": [1],
        "target_names": ["value"],
        "strategy": {"name": "one_step"},
        "trace": TRACE,
        "splits": {
            "validation": {
                "count": 3,
                "origin_start": origins[0].isoformat(),
                "origin_end": origins[-1].isoformat(),
                "label_end": str(table.target_timestamp.max()),
            }
        },
        "python": platform.python_version(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "pandas", "pyarrow", "synthetic-trial-application")
        },
        "source_sha256": {
            str(path.relative_to(package)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(package.rglob("*.py"))
        },
        "lock_sha256": hashlib.sha256((package.parent.parent / "uv.lock").read_bytes()).hexdigest(),
        "git_commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "git_dirty": bool(dirty.stdout.strip()) if dirty.returncode == 0 else None,
    }
    (output / "metrics.json").write_text(json.dumps(metrics))
    (output / "run.json").write_text(json.dumps(metadata))
    table.to_parquet(output / "predictions.parquet", index=False)
    (output / "figures").mkdir()
    for name in (
        "forecasts",
        "residuals",
        "per_horizon",
        "prices",
        "returns",
        "rolling_volatility",
        "correlations",
    ):
        (output / "figures" / f"{name}.json").write_text('{"data": []}')
        (output / "figures" / f"{name}.html").write_text("<html>synthetic</html>")
    return BenchmarkResult(output, metrics, metadata)

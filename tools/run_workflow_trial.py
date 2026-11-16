"""Developer-only paired trial for the reviewed loader/benchmark artifact contract.

Run with the explicitly selected runtime. This is not a general execution API or an
effect sandbox. Importing this script neither imports ML libraries nor runs a trial.
"""

# Optional runtime dependencies are loaded only for the selected developer operation.
# ruff: noqa: PLC0415

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

    import pandas as pd  # type: ignore[import-untyped]

MAX_JSON = 16 * 1024 * 1024
MAX_LOG = 65536
MAX_TIMEOUT = 300
REFERENCE_CALL_COUNT = 3
MODES = ("reference", "generated")
ARTIFACT_PATH = re.compile(r"artifacts/[a-z][a-z0-9_]{0,63}")


def require(condition: object, message: str) -> None:
    """Fail explicitly even when the interpreter uses optimization."""
    if not condition:
        raise ValueError(message)


def identity(path: Path) -> dict[str, Any]:
    """Hash a regular file with bounded reads."""
    require(path.is_file() and not path.is_symlink(), f"Not a regular file: {path}")
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
            size += len(block)
    return {"sha256": digest.hexdigest(), "size_bytes": size}


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        require(name not in result, "Duplicate JSON key")
        result[name] = value
    return result


def _nonfinite(value: str) -> None:
    raise ValueError(f"Nonfinite JSON number: {value}")


def read_json(path: Path) -> dict[str, Any]:
    """Read bounded strict JSON without duplicate keys or nonfinite values."""
    require(identity(path)["size_bytes"] <= MAX_JSON, "JSON exceeds 16 MiB")
    value = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_unique, parse_constant=_nonfinite
    )
    # Reject exponent overflow as well as explicit NaN/Infinity tokens.
    json.dumps(value, allow_nan=False)
    require(isinstance(value, dict), "Expected a JSON object")
    return cast("dict[str, Any]", value)


def write_json(path: Path, value: object) -> None:
    """Publish one exclusive observation, retaining earlier files unchanged."""
    content = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    require(len(content.encode("utf-8")) <= MAX_JSON, "Result exceeds 16 MiB")
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def _contained(root: Path, relative: str) -> Path:
    path = root / relative
    require(
        not Path(relative).is_absolute() and ".." not in Path(relative).parts,
        "Evidence path must be relative and contained",
    )
    require(path.resolve().is_relative_to(root.resolve()), "Evidence path escapes its root")
    current = path
    while current != root:
        require(not current.is_symlink(), "Evidence contains a symbolic link")
        current = current.parent
    return path


def environment() -> dict[str, str]:
    """Remove Python/Git overrides; local execution is not an environment sandbox."""
    result = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        result.pop(name, None)
    result.update(DO_NOT_TRACK="1", KEDRO_DISABLE_TELEMETRY="1")
    return result


def git_context(root: Path) -> dict[str, Any]:
    """Observe explicit Git context without hooks or optional index writes."""
    prefix = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(root)]
    commit = subprocess.run(
        [*prefix, "rev-parse", "--verify", "HEAD"],
        env=environment(),
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    ).stdout.strip()
    status = subprocess.run(
        [
            *prefix,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=normal",
            "--ignore-submodules=all",
        ],
        env=environment(),
        capture_output=True,
        timeout=15,
        check=True,
    ).stdout
    return {
        "commit": commit,
        "working_tree": "dirty" if status else "clean",
        "untracked_policy": "normal",
        "submodule_policy": "ignored",
    }


def _ambient_git(root: Path) -> dict[str, Any]:
    try:
        return {"status": "observed", **git_context(root)}
    except (OSError, subprocess.SubprocessError):
        return {"status": "unavailable"}


def runtime_metadata() -> dict[str, Any]:
    """Observe installed metadata independently of actual module import origins."""
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "executable": sys.executable,
        "distributions": sorted(
            (
                {"name": item.metadata["Name"], "version": item.version}
                for item in importlib.metadata.distributions()
            ),
            key=lambda item: item["name"].lower(),
        ),
    }


def load_definition(path: Path) -> dict[str, Any]:
    """Validate the bounded local worksheet, including all writable roots."""
    plan: dict[str, Any] = read_json(path)
    require(plan["document_kind"] == "local_validation_trial_proposal", "Unsupported worksheet")
    require(plan["candidate"]["phase"] == "validation", "Only validation scoring is supported")
    require(
        plan["candidate"]["estimator"] == "naive" and plan["candidate"]["strategy"] == "one_step",
        "Only the frozen naive/one_step candidate is supported",
    )
    require(
        plan["expectations"]["numeric_tolerance"]
        == {"absolute": 0, "relative": 0, "non_finite": "reject"},
        "Only exact comparisons supported",
    )
    require(
        plan["protocol"]["metrics"] == ["mae", "rmse"]
        and len(plan["protocol"]["target"]["horizons"]) == 1
        and len(plan["protocol"]["target"]["target_names"]) == 1
        and plan["protocol"]["split"]["gap_sessions"] == 0,
        "Unsupported metric/target/split contract",
    )
    require(
        ARTIFACT_PATH.fullmatch(plan["candidate"]["output"]) is not None,
        "Invalid application artifact path",
    )
    trial, project, source = (
        path.parent.resolve(),
        Path(plan["generated_project"]).resolve(),
        Path(plan["source_root"]).resolve(),
    )
    require(
        all(
            not trial.is_relative_to(root) and not root.is_relative_to(trial)
            for root in (source, project)
        ),
        "Trial overlaps a protected root",
    )
    reference = Path(plan["execution"]["reference"]["cwd"])
    require(
        reference.absolute() == trial / "reference" and not reference.is_symlink(),
        "Reference working directory must be the trial's new reference child",
    )
    require(
        Path(plan["execution"]["generated"]["cwd"]).resolve() == project,
        "Generated working directory differs from project",
    )
    for mode, root in (("reference", reference), ("generated", project)):
        expected = root / plan["candidate"]["output"]
        require(
            Path(plan["execution"][mode]["artifact_destination"]).absolute() == expected.absolute(),
            "Artifact destination differs from its declared root",
        )
        _contained(root, plan["candidate"]["output"])
    require(plan["execution"]["reference"]["candidate"] == plan["candidate"], "Candidate override")
    timeout = plan["execution"]["timeout_seconds_per_process"]
    require(
        type(timeout) is int and 0 < timeout <= MAX_TIMEOUT, "Timeout must be within 1..300 seconds"
    )
    require(plan["execution"]["automatic_retries"] == 0, "Retries are not supported")
    require(
        len(plan["execution"]["reference"]["calls"]) == REFERENCE_CALL_COUNT,
        "Reference requires exactly three declared calls",
    )
    plan["_definition_directory"] = str(path.parent)
    return plan


def verify_snapshot(plan: dict[str, Any], directory: Path, *, destinations_absent: bool) -> None:
    """Check protected bytes and metadata before and after worker execution."""
    report_path = _contained(directory, plan["provenance"]["frozen_copy"])
    require(
        identity(report_path) == {key: plan["provenance"][key] for key in ("sha256", "size_bytes")},
        "Frozen provenance drifted",
    )
    report = read_json(report_path)
    require(
        plan["publication_inventory"] == report["generation"]
        and plan["source_bindings"] == report["source"]["copies"]
        and plan["environment"] == report["environment"]
        and plan["source_git"] == report["source"]["git"],
        "Worksheet differs from frozen provenance",
    )
    project, source = Path(plan["generated_project"]), Path(plan["source_root"])
    inventory = plan["publication_inventory"]
    require(
        identity(project / "generation-inventory.json") == inventory["inventory"],
        "Inventory drifted",
    )
    for relative, expected in inventory["files"].items():
        require(
            identity(_contained(project, relative))
            == {key: expected[key] for key in ("sha256", "size_bytes")},
            f"Published file drifted: {relative}",
        )
    for staged, expected in plan["source_bindings"].items():
        relative = (
            staged.removeprefix("application/")
            if staged.startswith("application/")
            else plan["input_bindings"][staged]
        )
        require(
            identity(_contained(source, relative)) == expected, f"Original file drifted: {relative}"
        )
    require(git_context(source) == plan["source_git"], "Original Git context drifted")
    actual = runtime_metadata()
    require(actual == {key: plan["environment"][key] for key in actual}, "Runtime metadata drifted")
    require(
        Path(sys.executable).absolute() == Path(plan["selected_python"]).absolute(),
        "Use selected Python",
    )
    parameters = read_json(project / "conf/base/parameters.yml")
    require(
        parameters == {"candidate": plan["candidate"]}, "Generated parameters differ from trial"
    )
    policy = read_json(project / "artifact-policy.json")["destinations"]
    require(
        len(policy) == 1
        and policy[0]["parameter"] == "candidate"
        and policy[0]["key"] == "output"
        and policy[0]["path"] == plan["candidate"]["output"],
        "Artifact policy differs from trial",
    )
    protocol_input = Path(plan["execution"]["reference"]["inputs"]["protocol_path"])
    catalog = read_json(project / "conf/base/catalog.yml")
    for name in ("market_path", "protocol_path"):
        require(
            Path(plan["execution"]["reference"]["inputs"][name]).absolute()
            == _contained(project, catalog[name]["data"]).absolute(),
            "Reference inputs differ from catalog",
        )
    require(
        read_json(protocol_input) == plan["protocol"], "Protocol differs from frozen definition"
    )
    if destinations_absent:
        require(
            not Path(plan["execution"]["reference"]["cwd"]).exists(),
            "Reference root already exists",
        )
        for mode in ("reference", "generated"):
            target = Path(plan["execution"][mode]["artifact_destination"])
            require(
                not target.exists() and not target.is_symlink(),
                "Artifact destination already exists",
            )


def _symbol(name: str) -> Callable[..., Any]:
    require(re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", name) is not None, "Invalid symbol")
    module, _, attribute = name.rpartition(".")
    value = getattr(importlib.import_module(module), attribute)
    require(callable(value), "Declared symbol must be callable")
    return cast("Callable[..., Any]", value)


def observe_imports(plan: dict[str, Any]) -> dict[str, Any]:
    """Import explicitly selected modules and verify their observed source bytes."""
    project = Path(plan["generated_project"])
    report = read_json(Path(plan["_definition_directory"]) / plan["provenance"]["frozen_copy"])
    application_package = Path(report["source"]["package_root"]).name
    require(
        plan["expectations"]["result_type"].split(".")[0] == application_package,
        "Result type must belong to the original application package",
    )
    for name in plan["execution"]["reference"]["calls"]:
        require(
            name.startswith(application_package + "."), "Reference symbol outside original package"
        )
        value = _symbol(name)
        module = importlib.import_module(value.__module__)
        origin = (
            Path(cast("str", module.__file__)).resolve().relative_to(project.resolve()).as_posix()
        )
        require(
            origin in plan["source_bindings"],
            "Reference must call original source, not a proposed adapter",
        )
    registry = plan["execution"]["generated"]["registry"]
    suffix = ".register_pipelines()['__default__']"
    require(registry.endswith(suffix), "Unsupported registry declaration")
    registry_module = registry.removesuffix(suffix)
    with (project / "pyproject.toml").open("rb") as stream:
        generated_package = tomllib.load(stream)["tool"]["kedro"]["package_name"]
    require(
        registry_module == generated_package + ".pipeline_registry",
        "Registry differs from generated project",
    )
    importlib.import_module(registry_module)
    packages = (plan["expectations"]["result_type"].split(".")[0], registry_module.split(".")[0])
    evidence = {}
    for name, module in sorted(sys.modules.copy().items()):
        if name.split(".")[0] in packages:
            path = Path(cast("str", module.__file__)).resolve()
            require(
                path.is_relative_to(project.resolve()), f"Import outside generated project: {name}"
            )
            relative = path.relative_to(project.resolve()).as_posix()
            expected = plan["publication_inventory"]["files"][relative]
            require(
                identity(path) == {key: expected[key] for key in ("sha256", "size_bytes")},
                "Imported bytes drifted",
            )
            evidence[name] = {"path": str(path), **identity(path)}
    return evidence


def verify_consent(path: Path, definition: Path) -> dict[str, Any]:
    """Bind an operator declaration to exact artifacts; this does not authenticate a human."""
    declaration: dict[str, Any] = read_json(path)
    require(
        declaration["authorization"] == "execute_validation_pair"
        and isinstance(declaration["reviewed_by"], str)
        and bool(declaration["reviewed_by"].strip()),
        "Explicit reviewed execution declaration required",
    )
    require(
        declaration["definition_sha256"] == identity(definition)["sha256"]
        and declaration["harness_sha256"] == identity(Path(__file__))["sha256"],
        "Consent artifact binding differs",
    )
    plan = load_definition(definition)
    require(
        declaration["provenance_sha256"] == plan["provenance"]["sha256"],
        "Consent provenance binding differs",
    )
    return declaration


def worker(plan: dict[str, Any], mode: str, observation: Path) -> None:
    """Execute one reviewed path, retaining the typed result only in this process."""
    from kedro.config import OmegaConfigLoader
    from kedro.io import DataCatalog, MemoryDataset
    from kedro.runner import SequentialRunner

    require(
        Path.cwd().resolve() == Path(plan["execution"][mode]["cwd"]).resolve(),
        "Worker working directory differs",
    )
    target = Path(plan["execution"][mode]["artifact_destination"])
    require(not target.exists() and not target.is_symlink(), "Worker artifact destination exists")
    observe_imports(plan)
    cwd_git = _ambient_git(Path.cwd())
    if mode == "reference":
        calls = plan["execution"]["reference"]["calls"]
        require(
            len(calls) == REFERENCE_CALL_COUNT, "Reference requires exactly three declared calls"
        )
        inputs = plan["execution"]["reference"]["inputs"]
        dataset = _symbol(calls[0])(path=inputs["market_path"])
        protocol = _symbol(calls[1])(path=inputs["protocol_path"])
        result = _symbol(calls[2])(dataset=dataset, protocol=protocol, candidate=plan["candidate"])
    else:
        loader = OmegaConfigLoader(conf_source=str(Path.cwd() / "conf/base"))
        catalog = DataCatalog.from_config(loader["catalog"])
        for name, value in loader["parameters"].items():
            catalog[f"params:{name}"] = MemoryDataset(value)
        registry = plan["execution"]["generated"]["registry"].removesuffix(
            ".register_pipelines()['__default__']"
        )
        pipeline = importlib.import_module(registry).register_pipelines()["__default__"]
        SequentialRunner().run(pipeline, catalog)
        result = catalog.load("result")
    require(type(result) is _symbol(plan["expectations"]["result_type"]), "Unexpected result type")
    require(
        Path(result.directory).absolute()
        == Path(plan["execution"][mode]["artifact_destination"]).absolute(),
        "Result directory differs from declared destination",
    )
    write_json(
        observation,
        {
            "result_type": plan["expectations"]["result_type"],
            "directory": str(Path(result.directory).absolute()),
            "metrics": result.metrics,
            "metadata": result.metadata,
            "imports": observe_imports(plan),
            "cwd_git": cwd_git,
            "runtime": runtime_metadata(),
        },
    )


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _inventory(root: Path) -> dict[str, Any]:
    require(root.is_dir() and not root.is_symlink(), "Application artifact directory missing")
    result = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "Linked application artifact")
        require(path.resolve().is_relative_to(root.resolve()), "Artifact escapes its directory")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = identity(path)
    return result


def _check_table(plan: dict[str, Any], table: pd.DataFrame, metrics: dict[str, Any]) -> None:
    import numpy as np
    import pandas as pd

    require(
        list(table.columns) == plan["expectations"]["predictions_columns"] and len(table) > 0,
        "Prediction columns/rows differ",
    )
    protocol, target = plan["protocol"], plan["protocol"]["target"]
    require(
        set(table.horizon) == set(target["horizons"])
        and set(table.target) == set(target["target_names"])
        and set(table.asset) == set(protocol["assets"]),
        "Prediction coordinates differ from protocol",
    )
    require(not table.isna().any().any(), "Missing prediction values")
    require(
        not table.duplicated(["origin", "asset", "horizon", "target"]).any()
        and table.origin.is_monotonic_increasing,
        "Duplicate or reordered prediction coordinates",
    )
    for name in ("origin", "target_start", "target_timestamp"):
        require(
            pd.api.types.is_datetime64_any_dtype(table[name]),
            "Prediction timestamps must retain datetime dtype",
        )
    require(
        bool(
            (table.origin > pd.Timestamp(protocol["split"]["train_end"])).all()
            and (table.target_timestamp <= pd.Timestamp(protocol["split"]["validation_end"])).all()
        ),
        "Predictions escape validation partition",
    )
    require(
        bool(
            (table.origin < table.target_start).all()
            and (table.target_start <= table.target_timestamp).all()
        ),
        "Invalid prediction time coordinates",
    )
    values = table[["actual", "predicted"]].to_numpy(dtype=float)
    require(bool(np.isfinite(values).all()), "Nonfinite predictions")
    errors = values[:, 1] - values[:, 0]
    expected = {"mae": float(np.mean(np.abs(errors))), "rmse": float(np.sqrt(np.mean(errors**2)))}
    horizon, name = target["horizons"][0], target["target_names"][0]
    expected.update({f"{key}/h{horizon}/{name}": value for key, value in tuple(expected.items())})
    require(
        set(metrics) == set(plan["expectations"]["metric_keys"]) == set(expected),
        "Metric keys differ",
    )
    require(
        all(type(value) in (int, float) and math.isfinite(value) for value in metrics.values()),
        "Nonfinite or nonnumeric metric",
    )
    require(metrics == expected, "Metrics differ from independent recomputation")


def _check_metadata(plan: dict[str, Any], metadata: dict[str, Any], table: pd.DataFrame) -> None:
    protocol, candidate = plan["protocol"], plan["candidate"]
    frozen = {
        "phase": "validation",
        "seed": candidate["seed"],
        "estimator_name": candidate["estimator"],
        "benchmark_id": protocol["benchmark_id"],
        "benchmark_version": protocol["version"],
        "dataset_fingerprint": protocol["dataset_fingerprint"],
        "benchmark_fingerprint": hashlib.sha256(_canonical(protocol).encode()).hexdigest(),
        "horizons": protocol["target"]["horizons"],
        "target_names": protocol["target"]["target_names"],
        "selected_features": protocol["feature_names"],
    }
    require(
        all(_canonical(metadata.get(key)) == _canonical(value) for key, value in frozen.items()),
        "Run metadata differs from frozen trial",
    )
    summary = metadata["splits"]["validation"]
    require(
        summary["count"] == len(table)
        and summary["origin_start"] == table.origin.min().isoformat()
        and summary["origin_end"] == table.origin.max().isoformat(),
        "Validation split summary differs from predictions",
    )
    require(metadata["python"] == plan["environment"]["python"], "Reported Python differs")
    installed = {
        item["name"].lower().replace("_", "-"): item["version"]
        for item in plan["environment"]["distributions"]
    }
    require(
        all(
            installed.get(name.lower().replace("_", "-")) == version
            for name, version in metadata["packages"].items()
        ),
        "Reported package versions differ",
    )
    # Application source layout is explicit in the frozen report, not discovered by importing it.
    source_report = read_json(
        Path(plan["_definition_directory"]) / plan["provenance"]["frozen_copy"]
    )
    application_name = source_report["source"]["distribution"]["name"]
    require(
        application_name in metadata["packages"], "Application version missing from run metadata"
    )
    source_prefix = "application/" + source_report["source"]["package_root"] + "/"
    files = plan["publication_inventory"]["files"]
    expected_sources = {
        str(Path(relative.removeprefix(source_prefix))): item["sha256"]
        for relative, item in files.items()
        if relative.startswith(source_prefix) and relative.endswith(".py")
    }
    require(metadata["source_sha256"] == expected_sources, "Reported package source map differs")
    require(
        metadata["lock_sha256"] == files["application/uv.lock"]["sha256"],
        "Reported lock identity differs",
    )


def compare_artifacts(plan: dict[str, Any], observations: dict[str, Any]) -> dict[str, Any]:
    """Compare actual decoded artifacts; retain mismatches separately from execution errors."""
    import pandas as pd

    inventories, bundles, checks = {}, {}, []
    for mode in ("reference", "generated"):
        root = Path(plan["execution"][mode]["artifact_destination"])
        inventories[mode] = _inventory(root)
        try:
            require(
                set(inventories[mode]) == set(plan["expectations"]["required_files"]),
                "Missing or unexpected application artifact",
            )
            require(
                all(item["size_bytes"] > 0 for item in inventories[mode].values()), "Empty artifact"
            )
            protocol, metrics, metadata = (
                read_json(root / name) for name in ("protocol.json", "metrics.json", "run.json")
            )
            require(_canonical(protocol) == _canonical(plan["protocol"]), "Saved protocol differs")
            observation = observations[mode]
            require(
                observation["result_type"] == plan["expectations"]["result_type"]
                and Path(observation["directory"]) == root,
                "Observed result descriptor differs",
            )
            require(
                observation["runtime"]
                == {key: plan["environment"][key] for key in observation["runtime"]}
                and set(observation["runtime"])
                == {"python", "implementation", "executable", "distributions"},
                "Observed runtime differs",
            )
            require(
                _canonical(observation["metrics"]) == _canonical(metrics)
                and _canonical(observation["metadata"]) == _canonical(metadata),
                "Memory result differs from saved artifacts",
            )
            context = observation["cwd_git"]
            if context["status"] == "observed":
                require(
                    metadata["git_commit"] == context["commit"]
                    and metadata["git_dirty"] is (context["working_tree"] == "dirty"),
                    "Ambient Git metadata differs from worker observation",
                )
            else:
                require(
                    metadata["git_commit"] is None and metadata["git_dirty"] is None,
                    "Unexpected ambient Git metadata",
                )
            table = pd.read_parquet(root / "predictions.parquet")
            _check_table(plan, table, metrics)
            _check_metadata(plan, metadata, table)
            for relative in inventories[mode]:
                if relative.endswith(".json"):
                    read_json(root / relative)
            bundles[mode] = (metrics, metadata, table)
            checks.append({"check": f"{mode}_artifact_contract", "status": "passed"})
        except (ValueError, AssertionError, KeyError, TypeError) as error:
            checks.append(
                {
                    "check": f"{mode}_artifact_contract",
                    "status": "mismatch",
                    "diagnostic": str(error)[:1000],
                }
            )
    if len(bundles) == len(MODES):
        try:
            left, right = bundles["reference"], bundles["generated"]
            require(left[0] == right[0], "Paired metrics differ")
            exclusions = plan["expectations"]["allowed_contextual_metadata_differences"]
            require(exclusions == ["git_commit", "git_dirty"], "Unsupported metadata exclusions")
            require(
                _canonical({key: value for key, value in left[1].items() if key not in exclusions})
                == _canonical(
                    {key: value for key, value in right[1].items() if key not in exclusions}
                ),
                "Paired run metadata differs",
            )
            pd.testing.assert_frame_equal(
                left[2], right[2], check_dtype=True, check_exact=True, check_like=False
            )
            checks.append({"check": "paired_observations", "status": "passed"})
        except (ValueError, AssertionError) as error:
            checks.append(
                {
                    "check": "paired_observations",
                    "status": "mismatch",
                    "diagnostic": str(error)[:1000],
                }
            )
    return {
        "status": "matched_scoped_expectations"
        if len(checks) == len(MODES) + 1 and all(check["status"] == "passed" for check in checks)
        else "comparison_mismatch",
        "checks": checks,
        "artifact_inventories": inventories,
        "figure_equivalence": "not_checked",
        "scientific_performance_thresholds": "not_established",
    }


def _invoke(
    plan: dict[str, Any], definition: Path, consent: Path, mode: str, attempt: Path
) -> dict[str, Any]:
    command = [
        plan["selected_python"],
        "-I",
        str(Path(__file__).absolute()),
        str(definition),
        "--consent",
        str(consent),
        "--worker",
        mode,
    ]
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=plan["execution"][mode]["cwd"],
            env=environment(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=plan["execution"]["timeout_seconds_per_process"],
            check=False,
        )
        status, code, stdout, stderr = (
            "completed" if result.returncode == 0 else "execution_failed",
            result.returncode,
            result.stdout,
            result.stderr,
        )
    except subprocess.TimeoutExpired as error:
        status, code, stdout, stderr = "timeout", None, error.stdout or b"", error.stderr or b""
    for name, content in (("stdout", stdout), ("stderr", stderr)):
        with (attempt / f"{mode}.{name}.log").open("xb") as stream:
            stream.write(content[:MAX_LOG])
    return {
        "command": command,
        "cwd": plan["execution"][mode]["cwd"],
        "status": status,
        "exit_code": code,
        "duration_seconds": time.monotonic() - started,
        "stdout_truncated": len(stdout) > MAX_LOG,
        "stderr_truncated": len(stderr) > MAX_LOG,
    }


def execute_trial(definition: Path, consent: Path) -> dict[str, Any]:
    """Reserve an attempt before worker I/O; never retry or clean up artifacts."""
    plan = load_definition(definition)
    declaration = verify_consent(consent, definition)
    attempt = definition.parent / "attempt"
    attempt.mkdir()
    evidence: dict[str, Any] = {
        "status": "not_run",
        "definition": identity(definition),
        "provenance": plan["provenance"],
        "harness": identity(Path(__file__)),
        "consent": declaration,
        "consent_file": identity(consent),
        "invocations": [],
    }
    write_json(attempt / "reservation.json", evidence)
    plan["_definition_directory"] = str(definition.parent)
    try:
        verify_snapshot(plan, definition.parent, destinations_absent=True)
        evidence["preflight_imports"] = observe_imports(plan)
        Path(plan["execution"]["reference"]["cwd"]).mkdir()
        for mode in ("reference", "generated"):
            invocation = _invoke(plan, definition, consent, mode, attempt)
            evidence["invocations"].append(invocation)
            write_json(attempt / f"{mode}.invocation.json", invocation)
            evidence["status"] = invocation["status"]
            if invocation["status"] != "completed":
                break
        else:
            observations = {
                mode: read_json(attempt / f"{mode}.observation.json")
                for mode in ("reference", "generated")
            }
            evidence.update(compare_artifacts(plan, observations))
    except Exception as error:
        evidence.update(
            status="setup_or_comparison_error", diagnostic=f"{type(error).__name__}: {error}"
        )
    try:
        verify_snapshot(plan, definition.parent, destinations_absent=False)
        evidence["postflight"] = "protected_identities_match"
    except Exception as error:
        evidence.update(status="postflight_failed", postflight=f"{type(error).__name__}: {error}")
    inventories = {}
    for mode in ("reference", "generated"):
        root = Path(plan["execution"][mode]["artifact_destination"])
        try:
            inventories[mode] = _inventory(root) if root.exists() else {"status": "absent"}
        except (ValueError, OSError) as error:
            inventories[mode] = {"status": "inventory_failed", "diagnostic": str(error)}
    evidence["artifact_inventories"] = inventories
    write_json(attempt / "result.json", evidence)
    return evidence


def main(argv: list[str] | None = None) -> int:
    """Inspect a frozen trial, or explicitly execute an operator-consented pair."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("definition", type=Path)
    parser.add_argument("--consent", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--worker", choices=("reference", "generated"), help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    definition = arguments.definition.absolute()
    plan = load_definition(definition)
    if arguments.worker or arguments.execute:
        require(arguments.consent is not None, "Execution requires an explicit consent declaration")
        consent = arguments.consent.absolute()
        verify_consent(consent, definition)
        if arguments.worker:
            attempt = definition.parent / "attempt"
            reservation = read_json(attempt / "reservation.json")
            require(
                reservation["definition"] == identity(definition)
                and reservation["harness"] == identity(Path(__file__))
                and reservation["consent_file"] == identity(consent),
                "Worker differs from reserved attempt",
            )
            write_json(
                attempt / f"{arguments.worker}.started.json",
                {
                    "definition": identity(definition),
                    "cwd": str(Path.cwd()),
                    "mode": arguments.worker,
                },
            )
            verify_snapshot(plan, definition.parent, destinations_absent=False)
            worker(
                plan,
                arguments.worker,
                definition.parent / "attempt" / f"{arguments.worker}.observation.json",
            )
            return 0
        evidence = execute_trial(definition, consent)
        sys.stdout.write(
            json.dumps(
                {
                    "status": evidence["status"],
                    "result": str(definition.parent / "attempt/result.json"),
                }
            )
            + "\n"
        )
        return 0 if evidence["status"] == "matched_scoped_expectations" else 1
    verify_snapshot(plan, definition.parent, destinations_absent=True)
    imports = observe_imports(plan)
    sys.stdout.write(
        json.dumps(
            {
                "status": "preflight_passed",
                "definition": identity(definition),
                "harness": identity(Path(__file__)),
                "verified_imports": len(imports),
                "benchmark_execution": "not_run",
            }
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Opt-in measured installation journey for two fixed trusted synthetic financial models."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import platform
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING, Any

from notebook_to_kedro import (
    GenerateRequest,
    InspectRequest,
    KedroArchitectureProfile,
    PlanningResult,
    PlanRequest,
    load_local_project_configuration,
    measure_local_operation,
    prepare_effort_comparison,
    summarize_conversion_measurements,
)
from notebook_to_kedro.generation.writer import write_project

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/nested_financial"
CASES = ("credit_pipeline", "lapse_calibrated_vote")
MODEL_CHECKS = 2
RUNTIME_PACKAGES = ("numpy", "pandas", "scipy", "scikit-learn", "kedro", "kedro-datasets", "pytest")
LOGGER = logging.getLogger(__name__)

# Deliberate developer reference execution, never called by analysis/generation.
REFERENCE = """import json
import sys
from importlib.metadata import version
from pathlib import Path
import numpy as np
import pandas as pd

destination = Path(sys.argv[1])
namespace = {}
for cell in json.loads(Path("workflow.ipynb").read_text(encoding="utf-8"))["cells"]:
    if cell["cell_type"] == "code":
        exec(compile("".join(cell["source"]), "trusted_financial_reference", "exec"), namespace)
# Fixed validation positions span the year; selection uses no predictions or labels.
positions = [0, 1, 2, 3, 100, 200, 300, 400]
probe = namespace["X_validation"].iloc[positions]
probe.to_csv(destination / "probe.csv", index=False, lineterminator="\\n")
# Compute the reference against exactly the CSV representation delivered to tests.
probe = pd.read_csv(destination / "probe.csv")
checks = []
for method in ("predict", "predict_proba"):
    observed = getattr(namespace["fitted_model"], method)(probe)
    assert isinstance(observed, np.ndarray) and np.isfinite(observed).all()
    checks.append({
        "id": "reload-" + method.replace("_", "-"), "scenario": "baseline",
        "method": method, "input": {"kind": "csv", "fixture": "model-probe"},
        "expected": {"kind": "array", "dtype": str(observed.dtype), "data": observed.tolist()},
        "abs_tol": 1e-10 if method == "predict_proba" else 0, "rel_tol": 0,
    })
(destination / "reference.json").write_text(json.dumps({
    "oracle_basis": "captured_original_source", "independent_scientific_oracle": False,
    "probe_cohort": "validation", "positions": positions, "model_checks": checks,
    "python": sys.version,
    "versions": {name: version(name) for name in json.loads(sys.argv[2])},
}, indent=2, allow_nan=False) + "\\n", encoding="utf-8")
"""

CLI_RELOAD = """import json
import runpy
import sys
from pathlib import Path
from kedro.config import OmegaConfigLoader

root = Path.cwd()
sys.path.insert(0, str(root / "tests"))
manifest = json.loads((root / "tests/regression_cases.json").read_text(encoding="utf-8"))
storage = manifest["model_output"]
configuration = OmegaConfigLoader(conf_source="conf/base")["catalog"][storage["dataset"]]
assert configuration == storage["configuration"]
configuration["filepath"] = (root / configuration["filepath"]).as_posix()
base = Path(configuration["filepath"])
artifacts = list(base.glob("*/" + base.name))
assert len(artifacts) == 1
artifact = artifacts[0]
import hashlib
digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
for check in manifest["contract"]["model_checks"]:
    payload = {
        "dataset": storage["dataset"], "configuration": configuration,
        "version": artifact.parent.name, "artifact": str(artifact), "sha256": digest,
        "check": check,
    }
    path = Path(sys.argv[1])
    path.write_text(json.dumps(payload), encoding="utf-8")
    sys.argv = ["_model_reload_worker.py", str(path)]
    runpy.run_path(str(root / "tests/_model_reload_worker.py"), run_name="__main__")
assert hashlib.sha256(artifact.read_bytes()).hexdigest() == digest
print("CLI saved model matched both captured source probes")
"""


def _bootstrap() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "financial_bootstrap", ROOT / "tools/check_generated_bootstrap.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _source_files(case: str) -> dict[Path, str]:
    root = EXAMPLES / case
    return {
        path.relative_to(root): path.read_bytes().decode("utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _prepare_workspace(
    directory: Path, case: str, reference: dict[str, Any], *, custom: bool
) -> Path:
    files = _source_files(case)
    regression = json.loads(files[Path("regression.json")])
    probe = (directory / "capture/probe.csv").read_bytes()
    regression.update(schema_version="1.1", model_checks=reference["model_checks"])
    regression["fixtures"]["model-probe"] = {
        "path": "model-probe.csv",
        "sha256": hashlib.sha256(probe).hexdigest(),
    }
    settings = json.loads(files[Path("project-model.json")])
    settings["regression_contract"] = "regression-model.json"
    if custom:
        settings["architecture_profile"] = "journey-profile.json"
        files[Path("journey-profile.json")] = _json(
            KedroArchitectureProfile("financial.journey", "1.0.0", "training", "ml_").to_dict()
        )
    files.update(
        {
            Path("model-probe.csv"): probe.decode("utf-8"),
            Path("model-probe-reference.json"): _json(reference),
            Path("regression-model.json"): _json(regression),
            Path("project-journey.json"): _json(settings),
        }
    )
    workspace = directory / "workspace"
    write_project(workspace, files)
    return workspace


def _convert(directory: Path, workspace: Path, case: str) -> Path:
    configuration = load_local_project_configuration(workspace / "project-journey.json")
    ledger = directory / "attempts"
    preview: PlanningResult | None = None
    project = workspace / "project"
    for name, request in (
        ("01-inspect", InspectRequest(configuration)),
        ("02-plan", PlanRequest(configuration)),
        ("03-generate", GenerateRequest(configuration, project)),
    ):
        result = measure_local_operation(request, ledger / name, case_id=case)
        (directory / f"{name}.json").write_text(_json(result.to_dict()), encoding="utf-8")
        if isinstance(result, PlanningResult):
            preview = result
    assert preview is not None
    for file in preview.files:
        assert hashlib.sha256((project / file.path).read_bytes()).hexdigest() == file.sha256
    for copied in preview.copies:
        assert (
            hashlib.sha256((project / copied.destination).read_bytes()).hexdigest() == copied.sha256
        )
    prepare_effort_comparison(
        ledger,
        directory / "effort-comparison",
        operator="pending-human-measurement",
        acceptance_criteria=(
            "Source-free tests, Kedro CLI, exact-version reload and false-oracle rejection"
        ),
        setup_mode="reuse",
    )
    (directory / "JOURNEY.md").write_text(
        "# Prepared synthetic model journey\n\n"
        "Open `workspace/project-journey.json` with the VS Code extension's Choose Project "
        "Configuration command. Inspect source and Preview files use the same measured "
        "operations as this harness. Choose a new destination for another generation.\n\n"
        "`02-plan.json` preserves the exact preview. `workspace/project` is the generated "
        "project; `installed-project` contains copied tests/configuration/data and an empty "
        "src directory. Its package is installed in the sibling venv.\n\n"
        "`capture/reference.json` identifies predictions captured by explicit original-source "
        "execution, not independent scientific expectations. `evidence.json` records subsequent "
        "installation, test, CLI and reload outcomes. It may describe a partial failure.\n\n"
        "`attempts` records machine conversion time. The effort-comparison declarations are "
        "pending drafts: record configuration, adaptation, correction and review prospectively. "
        "Neither machine duration nor an empty draft establishes human savings. The VS Code "
        "interaction itself is not timed or automatically exercised by this harness.\n",
        encoding="utf-8",
    )
    return project


def _negative_control(
    bootstrap: ModuleType, directory: Path, runtime: Path, evidence: dict[str, Any]
) -> None:
    negative = directory / "false-oracle-project"
    shutil.copytree(runtime, negative)
    path = negative / "tests/regression_cases.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for check in data["contract"]["model_checks"]:
        expected = check["expected"]["data"]
        check["expected"]["data"] = (
            [1 - value for value in expected]
            if check["method"] == "predict"
            else [row[::-1] for row in expected]
        )
    path.write_text(_json(data), encoding="utf-8")
    report = directory / "false-oracle.xml"
    bootstrap._command(
        [
            str(bootstrap._python(directory)),
            "-I",
            "-m",
            "pytest",
            "-o",
            "pythonpath=",
            "-p",
            "no:cacheprovider",
            "-k",
            "model_reload",
            "--junitxml",
            str(report),
            "--basetemp",
            str(directory / "negative-tmp"),
            "-q",
        ],
        negative,
        directory / "false-oracle.log",
        evidence["stages"],
        expected_returncode=1,
    )
    _validate_negative_report(report)
    evidence["false_oracle_control"] = "rejected_after_storage"


def _validate_negative_report(report: Path) -> None:
    cases = ET.parse(report).getroot().findall(".//testcase")
    expected_names = {
        "test_model_reload[reload-predict]",
        "test_model_reload[reload-predict-proba]",
    }
    if (
        {case.get("name") for case in cases} != expected_names
        or len(cases) != MODEL_CHECKS
        or any(
            len(failures := case.findall("failure")) != 1
            or "Fresh model reload failed" not in failures[0].attrib.get("message", "")
            or case.find("error") is not None
            or case.find("skipped") is not None
            for case in cases
        )
    ):
        raise RuntimeError("False-oracle control must fail both fresh reload comparisons")


def check_case(directory: Path, case: str, *, custom: bool) -> dict[str, Any]:
    """Execute only one fixed synthetic case; retain partial evidence on any failure."""
    if case not in CASES:
        raise ValueError("Only the two committed synthetic financial cases are eligible")
    directory.mkdir()
    bootstrap = _bootstrap()
    original = bootstrap._inventory(EXAMPLES / case)
    evidence: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "started",
        "case": case,
        "profile": "custom" if custom else "default",
        "stages": [],
        "source_inventory": original,
        "oracle_basis": "captured_original_source",
        "environment": {"python": sys.version, "platform": platform.platform()},
        "independent_scientific_oracle": False,
        "human_effort": None,
        "baseline": None,
        "human_savings": None,
        "timing_scope": (
            "machine subprocess stages plus separate local-operation ledger; excludes human work"
        ),
    }
    (directory / "evidence.json").write_text(_json(evidence), encoding="utf-8")
    started = time.perf_counter_ns()
    try:
        write_project(directory / "reference-source", _source_files(case))
        capture = directory / "capture"
        capture.mkdir()
        bootstrap._command(
            [sys.executable, "-I", "-c", REFERENCE, str(capture), _json(RUNTIME_PACKAGES)],
            directory / "reference-source",
            directory / "reference.log",
            evidence["stages"],
        )
        reference = json.loads((capture / "reference.json").read_text(encoding="utf-8"))
        evidence["reference"] = reference
        constraints = directory / "runtime-constraints.txt"
        constraints.write_text(
            "".join(f"{name}=={value}\n" for name, value in reference["versions"].items()),
            encoding="utf-8",
        )
        evidence["runtime_constraints_sha256"] = hashlib.sha256(
            constraints.read_bytes()
        ).hexdigest()
        prepared = time.perf_counter_ns()
        workspace = _prepare_workspace(directory, case, reference, custom=custom)
        evidence["workspace_preparation_ns"] = time.perf_counter_ns() - prepared
        project = _convert(directory, workspace, case)
        protected = bootstrap._inventory(project)
        runtime = bootstrap._install_and_test(
            directory,
            project,
            evidence,
            package_name=case,
            expected_tests=12,
            constraints=constraints,
        )
        installed = {
            item["name"].lower(): item["version"] for item in evidence["runtime"]["distributions"]
        }
        if any(installed[name] != value for name, value in reference["versions"].items()):
            raise RuntimeError("Installed runtime differs from captured reference versions")
        inputs = {
            name: bootstrap._inventory(runtime / name) for name in ("conf", "data/01_raw", "tests")
        }
        bootstrap._command(
            [str(bootstrap._python(directory)), "-I", "-m", "kedro", "run"],
            runtime,
            directory / "kedro.log",
            evidence["stages"],
        )
        bootstrap._command(
            [
                str(bootstrap._python(directory)),
                "-I",
                "-c",
                CLI_RELOAD,
                str(directory / "cli-reload-payload.json"),
            ],
            runtime,
            directory / "cli-reload.log",
            evidence["stages"],
        )
        models = bootstrap._inventory(runtime / "data/06_models")
        if len(models) != 1:
            raise RuntimeError("Expected exactly one CLI-saved model version")
        evidence["cli_model_artifacts"] = models
        _negative_control(bootstrap, directory, runtime, evidence)
        if (
            bootstrap._inventory(project) != protected
            or inputs != {name: bootstrap._inventory(runtime / name) for name in inputs}
            or bootstrap._inventory(EXAMPLES / case) != original
        ):
            raise RuntimeError("Protected source, generated project, inputs or tests changed")
        if bootstrap._inventory(runtime / "data/06_models") != models:
            raise RuntimeError("CLI model changed during reloading or negative control")
        evidence.update(
            status="passed",
            preview_matches_publication=True,
            cli_reload="matched",
            source_unchanged=True,
            generated_project_unchanged=True,
            conversion_measurements=summarize_conversion_measurements(directory / "attempts"),
            regression_gaps=json.loads(
                (project / "regression-coverage.json").read_text(encoding="utf-8")
            ),
        )
        return evidence
    except BaseException as error:
        evidence.update(
            status="failed" if isinstance(error, Exception) else "interrupted",
            error={"type": type(error).__name__, "message": str(error)},
        )
        raise
    finally:
        evidence["elapsed_ns"] = time.perf_counter_ns() - started
        (directory / "evidence.json").write_text(_json(evidence), encoding="utf-8")


def main() -> None:
    """Run a new fixed-case batch; no arbitrary source, hidden retry or human timing claim."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--profile", choices=("default", "custom", "both"), default="both")
    arguments = parser.parse_args()
    destination = arguments.output.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    profiles = (False, True) if arguments.profile == "both" else (arguments.profile == "custom",)
    batch: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "started",
        "human_savings": None,
        "cases": [
            {"case": case, "profile": "custom" if custom else "default", "status": "not_run"}
            for case in CASES
            for custom in profiles
        ],
    }
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary_path = destination / "journey-summary.json"
    summary_path.write_text(_json(batch), encoding="utf-8")
    try:
        for item in batch["cases"]:
            item["status"] = "started"
            summary_path.write_text(_json(batch), encoding="utf-8")
            directory = destination / f"{item['case']}-{item['profile']}"
            try:
                result = check_case(directory, item["case"], custom=item["profile"] == "custom")
                item.update(status=result["status"], elapsed_ns=result["elapsed_ns"])
                summary_path.write_text(_json(batch), encoding="utf-8")
            except BaseException as error:
                item["status"] = "failed" if isinstance(error, Exception) else "interrupted"
                batch["status"] = item["status"]
                raise
        batch["status"] = "passed"
    finally:
        if batch["status"] == "started":
            batch["status"] = "failed"
        summary_path.write_text(_json(batch), encoding="utf-8")
    LOGGER.info("Financial model journeys passed; evidence: %s", destination)


if __name__ == "__main__":
    main()

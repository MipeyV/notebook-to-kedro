"""Opt-in installation checks for fixed trusted functional and procedural examples."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from contextlib import chdir
from pathlib import Path
from typing import Any

from notebook_to_kedro import (
    KedroArchitectureProfile,
    analyze_notebook_path,
    generate_functional_kedro_project,
    generate_kedro_project,
    load_functional_workflow_configuration,
    load_notebook_regression_contract,
    load_workflow_regression_contract,
    plan_notebook_path,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/functional_workflow"
PROCEDURAL_EXAMPLE = ROOT / "examples/procedural_regression"
EXPECTED_TESTS = 5
LOGGER = logging.getLogger(__name__)

_RUNTIME_PROBE = """import importlib
import importlib.util
import json
import sys
from importlib.metadata import distributions
from pathlib import Path

prefix = Path(sys.prefix).resolve()
module = Path(importlib.import_module(sys.argv[1]).__file__).resolve()
assert sys.prefix != sys.base_prefix
assert sys.flags.isolated
assert module.is_relative_to(prefix), module
assert importlib.util.find_spec("notebook_to_kedro") is None
assert "include-system-site-packages = false" in (
    prefix / "pyvenv.cfg"
).read_text(encoding="utf-8").lower()
print(json.dumps({
    "python": sys.version,
    "executable": sys.executable,
    "prefix": sys.prefix,
    "base_prefix": sys.base_prefix,
    "installed_module": str(module),
    "engine_available": False,
    "distributions": sorted(
        ({"name": item.metadata["Name"], "version": item.version} for item in distributions()),
        key=lambda item: item["name"].lower(),
    ),
}, sort_keys=True, indent=2))
"""

_PROCEDURAL_CLI_PROBE = '''import functools
import importlib
import importlib.util
import json
import math
import runpy
import sys
from pathlib import Path

import numpy as np
from kedro.runner import SequentialRunner

settings = json.loads(sys.argv[1])
report = Path(settings["report"])
assert not report.exists()
assert sys.flags.isolated and sys.prefix != sys.base_prefix
package = importlib.import_module("generated_procedural")
assert Path(package.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
assert importlib.util.find_spec("notebook_to_kedro") is None

if settings["mutation"]:
    nodes = importlib.import_module(settings["nodes_module"])
    original = getattr(nodes, settings["evaluation_node"])

    @functools.wraps(original)
    def changed(*args, **kwargs):
        predictions, error = original(*args, **kwargs)
        return predictions + 1, error

    setattr(nodes, settings["evaluation_node"], changed)


class ObservedRunner(SequentialRunner):
    """Observe the actual CLI run after delegating unchanged to SequentialRunner."""

    def run(self, *args, **kwargs):
        outputs = super().run(*args, **kwargs)
        assert set(outputs) == {"predictions", "error"}
        predictions = outputs["predictions"].load()
        error = outputs["error"].load()
        assert isinstance(predictions, np.ndarray) and str(predictions.dtype) == "float64"
        assert math.isfinite(error)
        observed = {"predictions": predictions.tolist(), "error": float(error)}
        matches = observed == {"predictions": [0.0, 1.0, 4.0, 9.0], "error": 0.0}
        report.write_text(json.dumps({
            "schema_version": "1.0", "mutation_applied": settings["mutation"],
            "runner_completed": True, "observations": observed,
            "status": "matched" if matches else "observation_mismatch",
        }, allow_nan=False, indent=2) + "\\n", encoding="utf-8")
        if not matches:
            raise AssertionError("Independent procedural observations differ")
        return outputs


sys.modules["bootstrap_verification"] = sys.modules["__main__"]
sys.argv = ["kedro", "run", "--runner", "bootstrap_verification.ObservedRunner"]
runpy.run_module("kedro", run_name="__main__")
'''


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    for name in (
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTEST_ADDOPTS",
        "VIRTUAL_ENV",
        "UV_PROJECT_ENVIRONMENT",
    ):
        environment.pop(name, None)
    environment.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", DO_NOT_TRACK="1")
    return environment


def _command(
    command: list[str],
    directory: Path,
    log: Path,
    stages: list[dict[str, Any]],
    *,
    expected_returncode: int = 0,
) -> None:
    stage: dict[str, Any] = {
        "command": command,
        "log": str(log),
        "status": "started",
        "expected_returncode": expected_returncode,
    }
    stages.append(stage)
    LOGGER.info("Running %s", log)
    started = time.perf_counter_ns()
    try:
        with log.open("w", encoding="utf-8") as stream:
            result = subprocess.run(
                command,
                cwd=directory,
                env=_environment(),
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=900,
                check=False,
            )
    finally:
        stage["duration_ns"] = time.perf_counter_ns() - started
    stage.update(
        returncode=result.returncode,
        status="passed" if result.returncode == expected_returncode else "failed",
    )
    if result.returncode != expected_returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); see {log}")


def _install_and_test(  # noqa: PLR0913
    directory: Path,
    project: Path,
    evidence: dict[str, Any],
    *,
    package_name: str,
    expected_tests: int = EXPECTED_TESTS,
    constraints: Path | None = None,
) -> Path:
    """Build a wheel and exercise shipped tests without engine or source-tree fallback."""
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("Install uv before running this opt-in check")
    stages = evidence["stages"]
    _command(
        [
            uv,
            "--no-config",
            "build",
            "--wheel",
            "--no-sources",
            "--out-dir",
            str(directory / "dist"),
        ],
        project,
        directory / "build.log",
        stages,
    )
    (wheel,) = (directory / "dist").glob("*.whl")
    evidence["wheel_sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
    _command(
        [sys.executable, "-I", "-m", "venv", "--copies", "--without-pip", str(directory / "venv")],
        directory,
        directory / "venv.log",
        stages,
    )
    python = _python(directory)
    _command(
        [uv, "--no-config", "pip", "install", "--python", str(python), f"{wheel}[test]"]
        + ([] if constraints is None else ["--constraint", str(constraints)]),
        directory,
        directory / "install.log",
        stages,
    )
    _command(
        [str(python), "-I", "-c", _RUNTIME_PROBE, package_name],
        directory,
        directory / "runtime.json",
        stages,
    )
    evidence["runtime"] = json.loads((directory / "runtime.json").read_text(encoding="utf-8"))
    runtime_project = directory / "installed-project"
    runtime_project.mkdir()
    for name in ("conf", "data", "tests"):
        shutil.copytree(project / name, runtime_project / name)
    shutil.copyfile(project / "pyproject.toml", runtime_project / "pyproject.toml")
    (runtime_project / "src").mkdir()
    _command(
        [
            str(python),
            "-I",
            "-m",
            "pytest",
            "-o",
            "pythonpath=",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(directory / "pytest-tmp"),
            "--junitxml",
            str(directory / "pytest.xml"),
            "-q",
            "--tb=short",
        ],
        runtime_project,
        directory / "pytest.log",
        stages,
    )
    report = ET.parse(directory / "pytest.xml").getroot()
    if len(report.findall(".//testcase")) != expected_tests or any(
        report.findall(f".//{kind}") for kind in ("failure", "error", "skipped")
    ):
        raise RuntimeError(f"Expected {expected_tests} executed, passing regressions")
    evidence["passed_tests"] = expected_tests
    return runtime_project


def _python(directory: Path) -> Path:
    return directory / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _check_case(
    directory: Path, suffix: str, profile: KedroArchitectureProfile | None
) -> dict[str, Any]:
    directory.mkdir()
    project = directory / "project"
    evidence: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "started",
        "source": f"workflow{suffix}",
        "profile": None if profile is None else profile.to_dict(),
        "source_sha256": hashlib.sha256((EXAMPLE / f"workflow{suffix}").read_bytes()).hexdigest(),
        "configuration_sha256": hashlib.sha256(
            (EXAMPLE / "workflow.json").read_bytes()
        ).hexdigest(),
        "expectations_sha256": hashlib.sha256(
            (EXAMPLE / "regression.json").read_bytes()
        ).hexdigest(),
        "stages": [],
    }
    try:
        generate_functional_kedro_project(
            EXAMPLE / f"workflow{suffix}",
            load_functional_workflow_configuration(EXAMPLE / "workflow.json"),
            project,
            project_root=ROOT,
            regression_contract=load_workflow_regression_contract(EXAMPLE / "regression.json"),
            architecture_profile=profile,
        )
        original_input = (project / "data/01_raw/values.json").read_bytes()
        original_parameters = (project / "conf/base/parameters.yml").read_bytes()
        stages = evidence["stages"]
        runtime_project = _install_and_test(
            directory, project, evidence, package_name="generated_workflow"
        )
        python = _python(directory)
        output = runtime_project / "data/08_reporting/total.json"
        if output.exists():
            raise RuntimeError("Regression tests wrote into the real project output")
        _command(
            [str(python), "-I", "-m", "kedro", "run"],
            runtime_project,
            directory / "kedro.log",
            stages,
        )
        if output.read_text(encoding="utf-8").strip() != "6.0":
            raise RuntimeError("kedro run did not persist the expected example result 6.0")
        if (runtime_project / "data/01_raw/values.json").read_bytes() != original_input or (
            runtime_project / "conf/base/parameters.yml"
        ).read_bytes() != original_parameters:
            raise RuntimeError("Example input or parameter files changed during execution")
        if (project / "data/08_reporting/total.json").exists():
            raise RuntimeError("Execution wrote output into the original generated project")
        evidence.update(status="passed", passed_tests=5, persisted_output=6.0)
        return evidence
    except Exception as error:
        evidence["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        if evidence["status"] != "passed":
            evidence["status"] = "failed"
        (directory / "evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
        )


def _inventory(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _check_observation_report(path: Path, *, mutation: bool) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "schema_version": "1.0",
        "mutation_applied": mutation,
        "runner_completed": True,
        "observations": {
            "predictions": [1.0, 2.0, 5.0, 10.0] if mutation else [0.0, 1.0, 4.0, 9.0],
            "error": 0.0,
        },
        "status": "observation_mismatch" if mutation else "matched",
    }
    if json.dumps(report, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True):
        raise RuntimeError("Unexpected independent CLI observation report")
    return report


def _observe_procedural_cli(
    directory: Path,
    runtime_project: Path,
    stages: list[dict[str, Any]],
    *,
    mutation: bool,
) -> dict[str, Any]:
    manifest = json.loads(
        (runtime_project / "tests/regression_cases.json").read_text(encoding="utf-8")
    )
    name = "negative-control" if mutation else "observed-cli"
    report = directory / f"{name}.json"
    settings = {
        "report": str(report),
        "mutation": mutation,
        "nodes_module": manifest["nodes_module"],
        "evaluation_node": manifest["nodes"]["task-0002"]["name"],
    }
    _command(
        [str(_python(directory)), "-I", "-c", _PROCEDURAL_CLI_PROBE, json.dumps(settings)],
        runtime_project,
        directory / f"{name}.log",
        stages,
        expected_returncode=1 if mutation else 0,
    )
    return _check_observation_report(report, mutation=mutation)


def _check_procedural_case(
    directory: Path,
    profile: KedroArchitectureProfile | None,
) -> dict[str, Any]:
    directory.mkdir()
    project = directory / "project"
    source = PROCEDURAL_EXAMPLE / "workflow.ipynb"
    evidence: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "started",
        "source_kind": "procedural",
        "source": "examples/procedural_regression/workflow.ipynb",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "expectations_sha256": hashlib.sha256(
            (PROCEDURAL_EXAMPLE / "regression.json").read_bytes()
        ).hexdigest(),
        "profile": None if profile is None else profile.to_dict(),
        "stages": [],
    }
    try:
        contract = load_notebook_regression_contract(PROCEDURAL_EXAMPLE / "regression.json")
        evidence.update(contract_sha256=contract.sha256, fixtures=contract.to_dict()["fixtures"])
        # The notebook generator's relative source-copy paths are rooted at the repository.
        with chdir(ROOT):
            generate_kedro_project(
                plan_notebook_path(source, project_root=ROOT),
                project,
                package_name="generated_procedural",
                architecture_profile=profile,
                source_facts=analyze_notebook_path(source, project_root=ROOT),
                regression_contract=contract,
            )
        original = _inventory(project)
        originals = {name: _inventory(project / name) for name in ("conf", "data")}
        runtime_project = _install_and_test(
            directory, project, evidence, package_name="generated_procedural"
        )
        stages = evidence["stages"]
        _command(
            [str(_python(directory)), "-I", "-m", "kedro", "run"],
            runtime_project,
            directory / "kedro.log",
            stages,
        )
        evidence["cli_observations"] = _observe_procedural_cli(
            directory, runtime_project, stages, mutation=False
        )
        evidence["negative_control"] = _observe_procedural_cli(
            directory, runtime_project, stages, mutation=True
        )
        if {name: _inventory(runtime_project / name) for name in ("conf", "data")} != originals:
            raise RuntimeError("Procedural input or configuration files changed during execution")
        if _inventory(project) != original:
            raise RuntimeError("Execution changed the original generated procedural project")
        evidence.update(
            status="passed",
            default_cli="passed",
            input_config_unchanged=True,
            generated_project_unchanged=True,
            regression_gaps=json.loads(
                (project / "regression-coverage.json").read_text(encoding="utf-8")
            ),
        )
        return evidence
    except Exception as error:
        evidence["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        if evidence["status"] != "passed":
            evidence["status"] = "failed"
        (directory / "evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
        )


def main() -> None:
    """Build/install/execute six fixed example variants; never accept arbitrary user code."""
    parser = argparse.ArgumentParser(description=__doc__)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser.add_argument("output", type=Path, help="New evidence directory (must not exist)")
    arguments = parser.parse_args()
    destination = arguments.output.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    for suffix in (".py", ".ipynb"):
        for name, profile in (
            ("default", None),
            ("custom", KedroArchitectureProfile("bootstrap.example", "1.0.0", "training", "ml_")),
        ):
            _check_case(destination / f"{suffix[1:]}-{name}", suffix, profile)
    for name, profile in (
        ("default", None),
        ("custom", KedroArchitectureProfile("bootstrap.example", "1.0.0", "training", "ml_")),
    ):
        _check_procedural_case(destination / f"procedural-{name}", profile)
    LOGGER.info("Six isolated installations passed; evidence: %s", destination)


if __name__ == "__main__":
    main()

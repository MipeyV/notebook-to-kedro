"""Opt-in network/install check for the repository's trusted functional example only."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from notebook_to_kedro import (
    KedroArchitectureProfile,
    generate_functional_kedro_project,
    load_functional_workflow_configuration,
    load_workflow_regression_contract,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/functional_workflow"
EXPECTED_TESTS = 5
LOGGER = logging.getLogger(__name__)

_RUNTIME_PROBE = """import importlib.util
import json
import sys
from importlib.metadata import distributions
from pathlib import Path

import generated_workflow

prefix = Path(sys.prefix).resolve()
module = Path(generated_workflow.__file__).resolve()
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


def _command(command: list[str], directory: Path, log: Path, stages: list[dict[str, Any]]) -> None:
    stage: dict[str, Any] = {"command": command, "log": str(log), "status": "started"}
    stages.append(stage)
    LOGGER.info("Running %s", log)
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
    stage.update(
        returncode=result.returncode, status="passed" if result.returncode == 0 else "failed"
    )
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); see {log}")


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
        # Standard venv supports signed CPython launchers on Windows as well as POSIX.
        _command(
            [
                sys.executable,
                "-I",
                "-m",
                "venv",
                "--copies",
                "--without-pip",
                str(directory / "venv"),
            ],
            directory,
            directory / "venv.log",
            stages,
        )
        python = directory / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        _command(
            [uv, "--no-config", "pip", "install", "--python", str(python), f"{wheel}[test]"],
            directory,
            directory / "install.log",
            stages,
        )
        _command(
            [str(python), "-I", "-c", _RUNTIME_PROBE], directory, directory / "runtime.json", stages
        )
        evidence["runtime"] = json.loads((directory / "runtime.json").read_text(encoding="utf-8"))
        # Run with real generated configuration/tests, but without any source-tree fallback.
        runtime_project = directory / "installed-project"
        runtime_project.mkdir()
        for name in ("conf", "data", "tests"):
            shutil.copytree(project / name, runtime_project / name)
        shutil.copyfile(project / "pyproject.toml", runtime_project / "pyproject.toml")
        (runtime_project / "src").mkdir()  # Kedro requires this directory, even when installed.
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
        if len(report.findall(".//testcase")) != EXPECTED_TESTS or any(
            report.findall(f".//{kind}") for kind in ("failure", "error", "skipped")
        ):
            raise RuntimeError("Expected five executed, passing node/pipeline regressions")
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


def main() -> None:
    """Build/install/execute four fixed example variants; never accept arbitrary user code."""
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
    LOGGER.info("Four isolated installations passed; evidence: %s", destination)


if __name__ == "__main__":
    main()

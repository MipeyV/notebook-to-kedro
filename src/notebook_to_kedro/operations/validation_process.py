"""Bounded subprocess supervision for explicitly requested generated tests."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from contextlib import suppress
from typing import TYPE_CHECKING, BinaryIO, cast

if TYPE_CHECKING:
    from pathlib import Path

MAX_LOG_BYTES = 2 * 1024 * 1024

WORKER = '''"""Execute the approved copied notebook suite; not a security sandbox."""
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import sys
import tomllib

ATTEMPT = Path(__file__).resolve().parent
ROOT = ATTEMPT / "project"
os.chdir(ROOT)
settings = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
requirements = settings["project"]["dependencies"] + ["pytest"]
versions, missing = {}, []
for requirement in requirements:
    name = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", requirement).group()
    try:
        versions[name] = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        missing.append(name)
environment = {
    "python": sys.executable, "version": platform.python_version(),
    "prefix": sys.prefix, "platform": platform.platform(),
    "distributions": versions, "missing": missing,
    "dependency_constraints": "not_evaluated", "installation": "not_performed",
}
(ATTEMPT / "environment.json").write_text(json.dumps(environment, sort_keys=True), encoding="utf-8")
if missing:
    print("Missing distributions: " + ", ".join(missing), flush=True)
    sys.exit(3)
import pytest
sys.path.insert(0, str(ROOT / "src"))
print("Environment checked; running supplied notebook tests", flush=True)
code = pytest.main([
    "-v", "--capture=no", "-c", str(ROOT / "pyproject.toml"), "--rootdir", str(ROOT),
    "--confcutdir", str(ROOT), "-o", "addopts=", "-o", "pythonpath=" + str(ROOT / "src"),
    "-p", "no:cacheprovider", "--basetemp", str(ATTEMPT / "pytest-temp"),
    "--junitxml", str(ATTEMPT / "pytest.xml"), str(ROOT / "tests/test_notebook_regressions.py"),
])
sys.exit(int(code))
'''


def _drain(stream: BinaryIO, destination: Path, truncated: threading.Event) -> None:
    """Continue draining output after the retained log reaches its byte budget."""
    retained = 0
    with stream, destination.open("wb") as target:
        while block := stream.read(8192):
            available = max(0, MAX_LOG_BYTES - retained)
            target.write(block[:available])
            retained += min(len(block), available)
            if len(block) > available:
                truncated.set()


def terminate_validation_process(process: subprocess.Popen[bytes]) -> None:
    """Terminate the worker process group/tree; this does not contain hostile code."""
    if sys.platform == "win32":
        with suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
    else:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)


def supervise_validation(
    python: Path,
    output: Path,
    timeout_seconds: int,
    cancel: threading.Event,
) -> tuple[str, int | None, bool]:
    """Run one selected interpreter, retaining bounded logs and terminal cancellation status."""
    if cancel.is_set():
        (output / "tests.log").write_bytes(b"")
        return "canceled", None, False
    environment = dict(os.environ)
    environment.update(
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTEST_ADDOPTS="",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUTF8="1",
        DO_NOT_TRACK="1",
        KEDRO_DISABLE_TELEMETRY="1",
    )
    for key in ("PYTHONPATH", "PYTHONHOME", "PYTEST_PLUGINS", "PYTEST_DEBUG"):
        environment.pop(key, None)
    creation_flags = (
        cast("int", vars(subprocess)["CREATE_NEW_PROCESS_GROUP"])
        | cast("int", vars(subprocess)["CREATE_NO_WINDOW"])
        if sys.platform == "win32"
        else 0
    )
    process = subprocess.Popen(
        [str(python), "-I", "-B", "-X", "utf8", "-u", str(output / "worker.py")],
        cwd=output / "project",
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=creation_flags,
        start_new_session=sys.platform != "win32",
    )
    truncated = threading.Event()
    log_failed = threading.Event()

    def drain() -> None:
        try:
            _drain(cast("BinaryIO", process.stdout), output / "tests.log", truncated)
        except OSError:
            log_failed.set()

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout_seconds
    status = "completed"
    try:
        while process.poll() is None:
            if cancel.is_set() or time.monotonic() >= deadline:
                status = "canceled" if cancel.is_set() else "timed_out"
                terminate_validation_process(process)
                break
            cancel.wait(0.05)
    finally:
        if process.poll() is None:
            terminate_validation_process(process)
        reader.join(timeout=5)
    if reader.is_alive():
        return "cleanup_incomplete", process.returncode, truncated.is_set()
    if log_failed.is_set():
        return "runner_error", process.returncode, truncated.is_set()
    if cancel.is_set():
        status = "canceled"
    return status, process.returncode, truncated.is_set()

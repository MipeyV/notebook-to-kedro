"""Stage original application metadata separately from the generated Kedro distribution."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from notebook_to_kedro.exceptions import FunctionalWorkflowError

if TYPE_CHECKING:
    from notebook_to_kedro.semantic.functional_workflow import FunctionalWorkflowPlan


def render_application_project(
    plan: FunctionalWorkflowPlan,
    root: Path,
    package_name: str,
    files: dict[Path, str],
    copies: tuple[tuple[Path, Path], ...],
) -> tuple[tuple[Path, Path], ...]:
    """Append raw project-file copies and explicit installation instructions."""
    distribution = plan.application_distribution
    if distribution is None:
        return copies
    if (
        re.sub(r"[-_.]+", "-", distribution.name).lower()
        == re.sub(r"[-_.]+", "-", package_name).lower()
    ):
        raise FunctionalWorkflowError(
            "Application distribution name collides with generated project"
        )
    directory = (root / distribution.pyproject).parent
    copied_targets = {target for _, target in copies}
    additions = tuple(
        (directory / item.path, Path("application") / item.path)
        for item in distribution.files
        if Path("application") / item.path not in copied_targets
    )
    files[Path("README.md")] = f"""# Generated Kedro workflow

The original application project is staged in `application/`, with its declared
distribution identity `{distribution.name}=={distribution.version}` and original
build configuration. Its source package retains its original relative layout.

Install both local projects from this directory in a compatible environment.

```sh
python -m pip install -e ./application -e .
```

Editable installation keeps application source-relative project-file lookups
anchored in `application/`. Select optional application extras explicitly when
needed, for example `-e './application[extra]'`. Review the original build backend,
selected build inputs and dependency declarations before installation. Builds and
dependency resolution run during installation. The manifest records their initial
status as `not_run`. Review compatible Python and dependency constraints for both
projects together. Copied lockfiles retain their original scope and paths.

Run the workflow from this directory after installation.

```sh
kedro run
```
"""
    return (*copies, *additions)

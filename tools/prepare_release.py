"""Verify and assemble this repository's engine/VSIX release bundle without publishing it."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

from notebook_to_kedro.generation.writer import write_project

REPOSITORY = "https://github.com/MipeyV/notebook-to-kedro"


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _versions(root: Path) -> tuple[str, str]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    engine = project["project"]["version"]
    extension = json.loads((root / "extensions/vscode/package.json").read_text(encoding="utf-8"))[
        "version"
    ]
    if not all(
        isinstance(value, str) and re.fullmatch(r"\d+\.\d+\.\d+", value)
        for value in (engine, extension)
    ):
        raise ValueError("Release versions must be numeric major.minor.patch values")
    tree = ast.parse((root / "src/notebook_to_kedro/__init__.py").read_text(encoding="utf-8"))
    exports = [
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
    ]
    locked = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    lock_versions = [
        package["version"]
        for package in locked["package"]
        if package["name"] == "notebook-to-kedro"
    ]
    node_lock = json.loads(
        (root / "extensions/vscode/package-lock.json").read_text(encoding="utf-8")
    )
    if (
        exports != [engine]
        or lock_versions != [engine]
        or node_lock["version"] != extension
        or node_lock["packages"][""]["version"] != extension
    ):
        raise ValueError("Engine/export/uv or extension/npm versions disagree")
    return str(engine), str(extension)


def _notes(root: Path, version: str) -> str:
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    section = re.search(
        rf"(?ms)^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}\n(.*?)(?=^## |\Z)", changelog
    )
    if section is None:
        raise ValueError("Release needs a dated changelog section")
    overview = re.search(r"(?ms)^### Release overview\n(.*?)(?=^### |\Z)", section[1])
    if overview is None or not overview[1].strip():
        raise ValueError("Release needs a nonempty changelog overview")
    return (
        overview[1].strip() + f"\n\n[Full changelog]({REPOSITORY}/blob/v{version}/CHANGELOG.md).\n"
    )


def _verify_engine(root: Path, wheel: Path, source: Path, version: str) -> None:
    modules = {
        path.relative_to(root / "src").as_posix(): path.read_bytes()
        for path in (root / "src/notebook_to_kedro").rglob("*.py")
    }
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if {
            name for name in names if name.startswith("notebook_to_kedro/") and name.endswith(".py")
        } != set(modules):
            raise ValueError("Wheel module inventory differs from source")
        for name, content in modules.items():
            if archive.read(name) != content:
                raise ValueError(f"Wheel module differs from source: {name}")
        metadata = archive.read(f"notebook_to_kedro-{version}.dist-info/METADATA").decode("utf-8")
        if f"Version: {version}" not in metadata.splitlines():
            raise ValueError("Wheel metadata version differs")
    with tarfile.open(source) as archive:
        prefix = f"notebook_to_kedro-{version}/"
        for name in ("pyproject.toml", "uv.lock", "CHANGELOG.md"):
            stream = archive.extractfile(prefix + name)
            if stream is None or stream.read() != (root / name).read_bytes():
                raise ValueError(f"Source distribution differs from checkout: {name}")
        for name, content in modules.items():
            stream = archive.extractfile(prefix + "src/" + name)
            if stream is None or stream.read() != content:
                raise ValueError(f"Source distribution module differs: {name}")


def _verify_extension(root: Path, vsix: Path, version: str) -> None:
    original = json.loads((root / "extensions/vscode/package.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(vsix) as archive:
        packaged = json.loads(archive.read("extension/package.json"))
        if packaged != original or packaged.get("version") != version:
            raise ValueError("VSIX metadata differs from the selected extension")
        compiled = list((root / "extensions/vscode/dist/src").glob("*.js"))
        if not compiled:
            raise ValueError("Compile the extension before verifying its package")
        if {
            name
            for name in archive.namelist()
            if name.startswith("extension/dist/src/") and name.endswith(".js")
        } != {"extension/dist/src/" + path.name for path in compiled}:
            raise ValueError("VSIX JavaScript inventory differs from compiled output")
        for path in compiled:
            if archive.read("extension/dist/src/" + path.name) != path.read_bytes():
                raise ValueError(f"VSIX JavaScript differs: {path.name}")


def prepare_release(  # noqa: PLR0913
    root: Path, artifacts: Path, vsix: Path, output: Path, *, commit: str, tag: str | None = None
) -> dict[str, object]:
    """Validate versions and actual built bytes, then publish one new local bundle.

    The workflow supplies the checked-out commit and enforces main ancestry. This function
    does not authenticate Git provenance, create tags or contact GitHub.
    """
    root, artifacts, vsix, output = (
        root.resolve(),
        artifacts.resolve(),
        vsix.resolve(),
        output.resolve(),
    )
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Release source commit must be a full lowercase Git SHA")
    engine, extension = _versions(root)
    release_tag = "v" + engine
    if tag is not None and tag != release_tag:
        raise ValueError("Tag differs from engine version")
    notes = _notes(root, engine)
    wheel = artifacts / f"notebook_to_kedro-{engine}-py3-none-any.whl"
    source = artifacts / f"notebook_to_kedro-{engine}.tar.gz"
    built = {path.name for path in artifacts.iterdir()}
    ignore = artifacts / ".gitignore"
    if ignore.is_file() and not ignore.is_symlink():
        with ignore.open("rb") as stream:
            if stream.read(4) in {b"*", b"*\n", b"*\r\n"}:
                built.discard(".gitignore")
    if built != {wheel.name, source.name}:
        raise ValueError(
            "Build directory must contain exactly the selected wheel and source archive"
        )
    assets = (wheel, source, vsix)
    if vsix.name != f"notebook-to-kedro-{extension}.vsix" or any(
        not path.is_file() or path.is_symlink() for path in assets
    ):
        raise ValueError("Release assets require the expected names and regular files")
    if (
        not output.is_relative_to(root / "generated")
        or output == root / "generated"
        or any(
            output == path or output in path.parents or path in output.parents
            for path in (*assets, root / "src", root / "extensions", root / "docs")
        )
    ):
        raise ValueError("Bundle output must be contained and disjoint from source and artifacts")
    _verify_engine(root, wheel, source, engine)
    _verify_extension(root, vsix, extension)
    entries = [
        {"name": path.name, "sha256": _digest(path), "bytes": path.stat().st_size}
        for path in assets
    ]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    extension_manifest = json.loads(
        (root / "extensions/vscode/package.json").read_text(encoding="utf-8")
    )
    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "tag": release_tag,
        "source_commit": commit,
        "engine_version": engine,
        "extension_version": extension,
        "prerelease": engine.startswith("0."),
        "python": project["project"]["requires-python"],
        "vscode": extension_manifest["engines"]["vscode"],
        "artifacts": entries,
    }
    content = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    checksums = {path.name: _digest(path) for path in assets}
    checksums.update(
        {
            "release-manifest.json": hashlib.sha256(content.encode()).hexdigest(),
            "RELEASE_NOTES.md": hashlib.sha256(notes.encode()).hexdigest(),
        }
    )
    files = {
        Path("release-manifest.json"): content,
        Path("RELEASE_NOTES.md"): notes,
        Path("SHA256SUMS"): "".join(
            f"{digest}  {name}\n" for name, digest in sorted(checksums.items())
        ),
    }
    write_project(output, files, tuple((path, Path(path.name)) for path in assets))
    if any(_digest(output / name) != digest for name, digest in checksums.items()):
        raise ValueError("Release bundle changed while copying; publication must not continue")
    return manifest


def main(argv: list[str] | None = None) -> int:
    """Build only local reviewable assets; external publication belongs to the tag workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--vsix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--tag")
    args = parser.parse_args(argv)
    manifest = prepare_release(
        args.root, args.artifacts, args.vsix, args.output, commit=args.commit, tag=args.tag
    )
    sys.stdout.write(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Bounded, read-only capture of a declared regular Python package and its resources."""

from __future__ import annotations

import ast
import hashlib
import keyword
import stat
import sys
from pathlib import Path, PurePosixPath

from notebook_to_kedro.analysis.functional_sources import MAX_PYTHON_BYTES, decode_python_source
from notebook_to_kedro.exceptions import FunctionalSourceError, FunctionalWorkflowError
from notebook_to_kedro.ir.source_package import PackageFile, PackageImport, SourcePackage

MAX_PACKAGE_FILES = 256
MAX_PACKAGE_BYTES = 16 * 1024 * 1024
MAX_PACKAGE_FILE_BYTES = 4 * 1024 * 1024
_REPARSE_POINT = 0x400
_COMPILED_SUFFIXES = frozenset({".pyc", ".pyo", ".pyd", ".so", ".dll"})


def _identifier(name: str) -> bool:
    return name.isascii() and name.isidentifier() and not keyword.iskeyword(name)


def _check_entry(path: Path) -> bool:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
        raise FunctionalWorkflowError(
            f"Source packages cannot contain links or reparse points: {path}"
        )
    if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
        raise FunctionalWorkflowError(f"Source packages require regular files/directories: {path}")
    return stat.S_ISDIR(info.st_mode)


def _module_name(package: Path, path: Path) -> str:
    relative = path.relative_to(package)
    components = (
        relative.parts[:-1] if path.name == "__init__.py" else (*relative.parts[:-1], path.stem)
    )
    if any(not _identifier(name) for name in components):
        raise FunctionalWorkflowError(
            f"Package module paths require ASCII Python identifiers: {path}"
        )
    parent = path.parent
    while parent != package:
        if not (parent / "__init__.py").is_file():
            raise FunctionalWorkflowError(f"Package module ancestors require __init__.py: {parent}")
        parent = parent.parent
    return ".".join((package.name, *components))


def _import_module(node: ast.ImportFrom, module: str, *, package_init: bool) -> str:
    if not node.level:
        return node.module or ""
    parents = module.split(".") if package_init else module.split(".")[:-1]
    if node.level > len(parents):
        raise FunctionalWorkflowError(f"Relative import escapes the declared package: {module}")
    prefix = parents[: len(parents) - node.level + 1]
    return ".".join((*prefix, *((node.module or "").split(".") if node.module else ())))


def capture_source_package(root: Path, selected: Path, relative_root: str) -> SourcePackage:
    """Capture files/imports without importing the package, following links or executing source."""
    root = root.resolve()
    portable = PurePosixPath(relative_root)
    if (
        not relative_root
        or portable.is_absolute()
        or ".." in portable.parts
        or portable.as_posix() != relative_root
        or "\\" in relative_root
        or ":" in relative_root
    ):
        raise FunctionalWorkflowError("source_package requires a contained relative POSIX path")
    package = root / relative_root
    try:
        # Check every path component before resolving; a contained link is still a link.
        current = root
        for component in Path(relative_root).parts:
            current /= component
            if not _check_entry(current):
                raise FunctionalWorkflowError("source_package must name a directory")
        package = package.resolve()
        selected = selected.resolve()
        if (
            not package.is_relative_to(root)
            or not selected.is_relative_to(package)
            or selected.suffix != ".py"
        ):
            raise FunctionalWorkflowError(
                "Package workflows require a .py source inside source_package"
            )
        name = package.name
        if (
            not _identifier(name)
            or name.startswith("_")
            or name in sys.stdlib_module_names
            or name in {"kedro", "kedro_datasets"}
        ):
            raise FunctionalWorkflowError(
                "Source package name conflicts with supported import namespaces"
            )
        captured, parsed, excluded = _capture_files(package)
        imports = _capture_imports(name, captured, parsed)
        source_file = selected.relative_to(package).as_posix()
        if source_file not in {item.path for item in captured}:
            raise FunctionalWorkflowError("Selected source is not a captured package file")
        return SourcePackage(
            relative_root,
            name,
            source_file,
            _module_name(package, selected),
            tuple(sorted(captured, key=lambda item: item.path)),
            imports,
            excluded,
        )
    except (OSError, SyntaxError, ValueError, FunctionalSourceError) as error:
        raise FunctionalWorkflowError(f"Cannot capture source package: {error}") from error


def _capture_file(package: Path, path: Path) -> tuple[PackageFile, ast.Module | None]:
    if path.suffix.lower() in _COMPILED_SUFFIXES:
        raise FunctionalWorkflowError(f"Compiled package files are unsupported: {path}")
    limit = MAX_PYTHON_BYTES if path.suffix == ".py" else MAX_PACKAGE_FILE_BYTES
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise FunctionalWorkflowError("Source package exceeds the supported file byte limit")
    module, ast_hash, tree = None, None, None
    if path.suffix == ".py":
        module = _module_name(package, path)
        text = decode_python_source(content, str(path))
        tree = ast.parse(text, filename=str(path))
        compile(text, str(path), "exec", dont_inherit=True)
        ast_hash = hashlib.sha256(ast.dump(tree).encode()).hexdigest()
    return PackageFile(
        path.relative_to(package).as_posix(),
        hashlib.sha256(content).hexdigest(),
        len(content),
        module,
        ast_hash,
    ), tree


def _capture_files(
    package: Path,
) -> tuple[list[PackageFile], list[tuple[str, str, bool, ast.Module]], tuple[str, ...]]:
    if not (package / "__init__.py").is_file():
        raise FunctionalWorkflowError(f"Regular source packages require __init__.py: {package}")
    pending = [package]
    captured: list[PackageFile] = []
    parsed: list[tuple[str, str, bool, ast.Module]] = []
    excluded: list[str] = []
    total = 0
    while pending:
        directory = pending.pop()
        for path in sorted(directory.iterdir()):
            is_directory = _check_entry(path)
            relative = path.relative_to(package).as_posix()
            if is_directory:
                if path.name == "__pycache__":
                    excluded.append(relative)
                else:
                    pending.append(path)
                continue
            if len(captured) == MAX_PACKAGE_FILES:
                raise FunctionalWorkflowError("Source package exceeds 256 files")
            item, tree = _capture_file(package, path)
            total += item.size_bytes
            if total > MAX_PACKAGE_BYTES:
                raise FunctionalWorkflowError("Source package exceeds the total byte limit")
            captured.append(item)
            if tree is not None:
                assert item.module is not None
                parsed.append((relative, item.module, path.name == "__init__.py", tree))
    return captured, parsed, tuple(sorted(excluded))


def _capture_imports(
    name: str, captured: list[PackageFile], parsed: list[tuple[str, str, bool, ast.Module]]
) -> tuple[PackageImport, ...]:
    modules = {item.module for item in captured if item.module is not None}
    imports: list[PackageImport] = []
    for relative, module, package_init, tree in sorted(parsed):
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [_import_module(node, module, package_init=package_init)]
            else:
                continue
            for imported in names:
                local = imported.split(".")[0] == name
                if local and imported not in modules:
                    raise FunctionalWorkflowError(
                        f"Local package import has no captured module: {imported}"
                    )
                imports.append(PackageImport(relative, node.lineno, imported, local))
    return tuple(imports)

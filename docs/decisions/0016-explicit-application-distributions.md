# ADR 0016 - Preserve an explicitly selected application distribution

Accepted on 2026-11-16.

[Documentation index](../README.md)

## Context

Application code can query its original distribution version through `importlib.metadata`,
load packaged resources and inspect files relative to its source layout. The package-only
conversion contract captures importable files. Distribution identity, dependency declarations,
build configuration and project-level provenance files require additional source evidence.

## Decision

Workflow schema 1.7 inherits schema 1.6 and requires an `application_project` selection with a
project-root-relative `pyproject` path and an explicit `files` list relative to that metadata
directory. Use standard-library TOML parsing to capture static PEP 621 name, version, Python
requirement, dependencies, extras and script declarations. Require static version/dependency
fields to bind the generated application's exact requirement. Preserve the complete original
pyproject bytes, including backend and tool settings.

Capture the pyproject, its referenced readme and license files and explicitly selected build
or provenance inputs. Apply contained regular-file checks, byte limits and SHA-256 inventories.
Bind metadata to the selected source package's original relative layout. Recapture before
rendering and reject drift. The pyproject has a 64 KiB limit and selected project files have a
256 MiB aggregate limit. Supporting source-package and raw-input budgets apply independently.

Stage this original project under `application/` through the shared project writer. Preserve its
source layout and namespace there. The generated Kedro distribution owns its generated package
and declares `<application-name>==<version>` as a dependency. Reject normalized distribution-name
collisions in addition to existing import-namespace collisions. Each distribution's own build
backend supplies its installed metadata.

Deliver explicit installation instructions for both local projects, using editable installation
to preserve source-relative project-file lookups. Optional application extras are selected by
the operator. Copied lockfiles retain their original scope and path declarations. Builds,
backend hooks, requirement validation, dependency resolution and installation are later actions.

Plan/manifest schema 1.6 records the captured declarations and project-file identities, with a
separate metadata digest and `not_run` build/resolution statuses. Source-package inventory retains
its existing observation scope. Local operations expose the selected file hashes and generated
setup instructions through the existing preview and publication paths.

## Consequences

The trusted synthetic fixture builds original and generated wheels, installs them offline into
temporary environments and exercises real distribution metadata, console-script declarations,
resources, shipped node/pipeline tests and the Kedro CLI. An editable-wheel variant also checks
the project-relative auxiliary-file hash. These checks reuse the locked development runtime's
dependencies through an explicit site path. Fresh dependency resolution remains a separate
evidence dimension.

The original backend may require additional selected inputs or dependency/build capabilities.
The static capture records declarations for review. Backend execution and dependency resolution
establish installability for the chosen environment. Installed wheel layouts can change the
meaning of source-relative paths, while editable installation retains the staged source layout.

The real-project check captures declarations and existing source/input hashes read-only. Its
actual selected module still requires an adopted orchestration entrypoint. Scientific/runtime
expectations and a separately scoped execution remain outstanding. Human pilot review is pending.

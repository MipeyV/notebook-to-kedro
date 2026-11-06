# Kedro architecture profiles

[Documentation index](../README.md)

Status: initial deterministic single-pipeline profile implemented. Schema `1.0` controls
pipeline organization and function/node naming only. It is not a complete enterprise
compliance engine, a general template system or a greenfield project generator.

## Reuse a profile

Keep the [example profile](../../examples/kedro_profiles/team_training.json), or your own
configuration, in version control. Review the plan before generating a new destination:

```bash
notebook-to-kedro plan tests/fixtures/notebooks/simple_training.ipynb \
  --architecture-profile examples/kedro_profiles/team_training.json

notebook-to-kedro generate tests/fixtures/notebooks/simple_training.ipynb \
  generated/team_project --package-name team_project \
  --architecture-profile examples/kedro_profiles/team_training.json
```

The example puts the pipeline in `src/team_project/pipelines/training/`, registers it as
`training` and `__default__`, and names functions/nodes `ml_load_data`, `ml_split_data`, etc.
It does not split the workflow into new stages or change execution dependencies.

The Python API accepts the same immutable profile object:

```python
from notebook_to_kedro import (
    generate_kedro_project,
    load_kedro_profile,
    plan_notebook_path,
    render_conversion_report,
)

profile = load_kedro_profile("examples/kedro_profiles/team_training.json")
plan = plan_notebook_path("tests/fixtures/notebooks/simple_training.ipynb")
report = render_conversion_report(plan, architecture_profile=profile)
created = generate_kedro_project(
    plan, "generated/team_project", package_name="team_project", architecture_profile=profile
)
```

`KedroArchitectureProfile` also supports direct construction and deterministic
`to_dict()`, `to_json()` and `from_dict()` round trips. `DEFAULT_KEDRO_PROFILE` is available
from the package root.

## Schema 1.0

```json
{
  "schema_version": "1.0",
  "profile_id": "example.team-training",
  "profile_version": "1.0.0",
  "pipeline_name": "training",
  "node_name_prefix": "ml_"
}
```

| Field | Contract |
| --- | --- |
| `schema_version` | Required string, exactly `1.0`. Other schemas are rejected. |
| `profile_id` | Required identifier: starts with a lowercase ASCII letter; remaining lowercase letters, digits, `_`, `.` or `-`; at most 128 characters. |
| `profile_version` | Required string with three numeric components. Bump it when changing conventions; no external version registry is enforced. |
| `pipeline_name` | Optional; defaults to `notebook_pipeline`. Public lowercase ASCII Python identifier, excluding keywords and Windows device names. Used for the one pipeline directory, module import and registry key. |
| `node_name_prefix` | Optional; defaults to empty. Otherwise lowercase ASCII letters/digits/underscores, starting with a letter and ending with `_`. Prepended to each function and Kedro node name. |

All values must be strings. Unknown/duplicate fields, unsupported schemas, malformed UTF-8/JSON
and files larger than 64 KiB raise `KedroProfileError`, a `ProjectGenerationError` subclass.
The loader does not import packages, execute templates or contact a provider.
Schema/loading errors are reported before CLI notebook planning; plan-specific compatibility
is checked after planning, without altering the supplied plan.

## Compatibility and fidelity

Explicit profiles reject invalid/duplicate normalized Python names and collisions with import
bindings or builtins. Imports must be explicit absolute import statements; wildcard/relative
imports cannot be checked by this slice. Compatibility errors are visible in `plan` and prevent
publication in `generate`. Ordinary plan validation, Python compilation and writer checks still apply.

Node names are presentation/organization choices. Source bodies, function arguments, parameter
keys, dataset names (including versioned redefinitions), catalog configuration and task provenance
remain source-derived. The profile does not rename business variables or relax code-fidelity checks.
Required stages, arbitrary layouts, dataset naming rules, tests/CI templates, tracking and migration
are outside schema 1.0; unsupported fields fail rather than being silently ignored.

## Review and generated evidence

With an explicit profile, the conversion report shows profile identity/version, a SHA-256 of the
normalized configuration and a task-to-generated-name mapping. Generation writes
`architecture-profile.json` with manifest schema `1.0`, the normalized profile/hash, notebook path,
stable task IDs, source names, generated names, source cell IDs and statement IDs.
Whitespace/key order and omitted default convention fields do not change the profile hash.

Check the report's hash against the generated manifest if the configuration may have changed
between review and generation. This is a declaration, not a signed approval, full source-byte
binding, enforced version registry or behavioral-equivalence proof.

Omitting the profile keeps the existing output inventory and bytes. Explicitly selecting the
default keeps those files byte-identical and adds only the manifest. Supported fixtures and the
draft complete pilot verify preserved behavior under the example profile, including real CSV
loading. The pilot's independent human review remains pending; these tests do not approve it or
establish arbitrary-notebook or production readiness.

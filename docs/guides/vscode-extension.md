# VS Code extension

[Documentation index](../README.md)

Status: first desktop prototype implemented on 2026-11-14. The Explorer's **Notebook to Kedro**
view selects a local configuration and Python interpreter, displays inspection diagnostics,
opens file previews and generates into a new project folder.

## Install and start

Build the engine environment from the repository with `uv sync --locked`, or install its
wheel into a Python 3.11/3.12/3.13 environment. Build the extension with Node 22+ and npm:

```bash
cd extensions/vscode
npm ci
npm run package
```

Install `generated/notebook-to-kedro-0.2.1.vsix` using **Extensions: Install from VSIX**.
The initial extension targets desktop VS Code 1.145+. Open Explorer's **Notebook to Kedro**
view and choose the Python executable containing the engine. **Create Project Configuration**
provides guided setup, and **Choose Project Configuration** opens an existing JSON file.
The command palette exposes the same actions under **Notebook to Kedro**.
Folder settings store the interpreter choice when the configuration belongs to a workspace
folder. User settings are used otherwise. The selected configuration is remembered per workspace.

The repository's [functional example](../../examples/local_operations/functional.json) and
[notebook example](../../examples/local_operations/notebook.json) are ready to use. **Edit Project
Configuration** opens the normal JSON editor for source, profile, I/O and expectation settings.
The [local operations contract](../reference/local-operations.md) defines those authoritative fields.

## Create a configuration

The assistant asks for the project folder, saved source, package name and optional profile.
Notebook inputs offer procedural or functional interpretation. A Python script selects the
functional path. Source/profile/expectation paths stay relative to the chosen project root.

For functional inputs, **Inspect functions first** allows static inspection before workflow
I/O is defined. Choose an existing workflow I/O file when those boundaries are available.
Planning and generation require that file. Optional regression expectations keep their
existing explicit-oracle contract. The assistant preserves missing expectations as gaps.

Choose a new JSON filename to finish. A temporary settings file is checked through the Python
configuration loader and source inspector before the destination is created exclusively.
Canceling a dialog creates no project settings. Existing files are preserved. The created file
is selected and opened, and static diagnostics appear even for blocked source. The selected
interpreter is applied to the new configuration's VS Code settings scope. Source files retain
their saved contents. Inspection validates source and local settings. Referenced workflow,
profile and expectation contents are checked by the existing planning/generation loaders.

Use an engine built from this revision for inspection without workflow I/O. Existing fully
configured operations keep their schema 1.0 behavior. Settings stay editable in the JSON editor.

## Inspect, preview and generate

**Inspect source** displays the engine's static status and diagnostics. **Open operation report**
shows the complete JSON facts. A blocked inspection retains its diagnostic information.

**Preview files** displays the actual generated file inventory and **Files to copy**. Selecting a
file opens a read-only virtual document containing its exact proposed bytes. Reports and
previews remain in memory, and source files retain their saved contents.

With an engine from this revision and an explicit schema 1.3 workflow configuration, copied
files also include the declared local Python package and its resources. The engine preserves
original import names and records the package inventory in the plan. This is not automatic
project/dependency discovery; select the existing package-aware workflow JSON through setup
or settings. Source-only inspection remains independent of its package context.

An engine from this revision also accepts schema 1.4 file-reference inputs with explicit sibling
sidecars. The same Files to copy tree lists their actual staged destinations and the operation
report retains raw-byte identities. Select the existing workflow JSON through setup/settings;
the UI does not infer loaders or sidecars. These inputs do not yet support the JSON regression
expectation contract. Local-operation schema and extension runtime behavior stay unchanged.

Schema 1.5 can explicitly choose a memory-only final result. Its preview/report shows
`result_boundary` and the memory catalog entry without running a pipeline or serializing an
application object into the interface. This does not persist results after a process ends.

**Generate project** refreshes the plan, asks for a destination inside the declared project
root and displays an explicit destination confirmation. Canceling that confirmation leaves
the destination absent. Confirming invokes the current Python generation operation, which
recomputes saved inputs and publishes through the shared staging writer. Existing targets
produce the engine's no-overwrite error. The returned file inventory opens the generated files.

Save source/configuration edits before using the operations. A preview records a particular
inspection, and generation reads current saved files. A review-hash-bound apply contract
remains future work. Engine output records errors and import/schema problems in the selected
Python environment. Install/update the engine there when its CLI is unavailable.

## Runtime and verification

The TypeScript extension starts the selected Python executable with isolated imports and
separate argument values using `execFile`. CLI schema 1.0 results are checked before display,
including status/exit-code agreement, relative file paths and preview content hashes. Each
process has a 120-second timeout and 64 MiB response limit. Inspection/preview can be canceled.
Commands are serialized, configuration/interpreter changes clear old results, and extension
disposal interrupts an active engine process. Interrupted generation can require checking
the destination before retrying because publication may already have completed.

VS Code Workspace Trust governs activation, and this prototype uses local file workspaces.
The Python engine owns source interpretation, profiles, rendering and publication. The
extension's processes perform static operations and project generation. Installing generated
dependencies and running ML project code remain explicit follow-up actions.

```bash
cd extensions/vscode
npm ci
npm run format:check
npm test
npm run test:host
npm run package
```

For host tests, set `NTK_TEST_PYTHON` to an absolute engine interpreter path. The runner uses
pinned VS Code 1.145.3 with private fixture/workspace, user-data and extension directories.
`VSCODE_EXECUTABLE_PATH` optionally selects an installed executable. Default testing downloads
an isolated archive. Host tests exercise actual extension activation/commands, read-only user
typing, cancellation before generation, confirmed generation, procedural notebook inspection,
preview and blocked diagnostics. Protocol tests cover malformed/schema-incompatible responses,
exit codes, traversal, content drift and argument separation. CI runs host checks under Xvfb
with locked Node tooling and locked core-only Python dependencies, then packages a VSIX artifact.

The initial setup assistant creates project settings and selects existing profile/I/O files.
Authoring business-specific I/O mappings, automatic Python-extension environment integration,
remote-workspace validation, Marketplace
publication, requirements generation and existing-project patching have their own later scope.

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

Install `generated/notebook-to-kedro-0.1.0.vsix` using **Extensions: Install from VSIX**.
The initial extension targets desktop VS Code 1.145+. Open Explorer's **Notebook to Kedro**
view, choose an existing local project JSON file, and choose the Python executable containing
the engine. The command palette exposes the same actions under **Notebook to Kedro**.
Folder settings store the interpreter choice when the configuration belongs to a workspace
folder. User settings are used otherwise. The selected configuration is remembered per workspace.

The repository's [functional example](../../examples/local_operations/functional.json) and
[notebook example](../../examples/local_operations/notebook.json) are ready to use. **Edit Project
Configuration** opens the normal JSON editor for source, profile, I/O and expectation settings.
The [local operations contract](../reference/local-operations.md) defines those authoritative fields.

## Inspect, preview and generate

**Inspect source** displays the engine's static status and diagnostics. **Open operation report**
shows the complete JSON facts. A blocked inspection retains its diagnostic information.

**Preview files** displays the actual generated file inventory and copied inputs. Selecting a
file opens a read-only virtual document containing its exact proposed bytes. Reports and
previews remain in memory, and source files retain their saved contents.

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

This first release uses explicit JSON editing and interpreter selection. Source/profile wizards,
automatic Python-extension environment integration, remote-workspace validation, Marketplace
publication, requirements generation and existing-project patching have their own later scope.

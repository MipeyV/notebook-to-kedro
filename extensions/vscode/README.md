# Notebook to Kedro for VS Code

Inspect local notebook or functional workflow projects, review generated files and generate a
Kedro project from the Explorer's **Notebook to Kedro** view.

## Setup

1. Install the Notebook to Kedro Python engine into a Python 3.11, 3.12 or 3.13 environment.
   From the repository, use `uv sync --locked`. Released engine wheels can also be installed
   into the environment you choose.
2. Install the VSIX through **Extensions: Install from VSIX**.
3. Open the project folder and the **Notebook to Kedro** view in Explorer.
4. Choose a local project configuration JSON and the Python executable containing the engine.
   Interpreter selection is saved in VS Code's folder settings, or user settings when the
   configuration belongs to no workspace folder.

The repository provides `examples/local_operations/functional.json` and `notebook.json`.
Use **Edit Project Configuration** to edit the source, source kind, workflow configuration,
architecture profile and optional regression expectations with the normal JSON editor.

## Use

- **Inspect source** displays static status and diagnostics. **Open operation report** shows
  the complete JSON facts.
- **Preview files** displays proposed files and copied inputs. Clicking a file opens its exact
  content in a read-only editor.
- **Generate project** refreshes the plan, asks for a new folder inside the declared project
  root, and displays a final destination confirmation. The engine recomputes current saved
  inputs and publishes through its staging writer. Existing destinations produce an error.
- **Show Engine Output** provides process and engine diagnostics. Install or update the
  engine in the selected interpreter if it reports an import or schema error.

Source and configuration are read from disk. Save edits before invoking an operation.
Generation uses current saved inputs. Re-run Preview when reviewing changes between actions.
Inspection and preview can be canceled. Generation completion is recorded by the returned
file inventory. An interrupted process can require checking the destination before retrying.

This initial desktop extension targets VS Code 1.145+, schema 1.0 local operations and local
file workspaces. Calls use an explicit interpreter with isolated Python imports, separate
process arguments and a 120-second timeout / 64 MiB response limit. Runtime dependencies of
the generated ML project are installed separately when you intend to execute it.

## Development

```bash
cd extensions/vscode
npm ci
npm test
npm run package
```

The package command creates `generated/notebook-to-kedro-0.1.0.vsix` at the repository root.
Set `NTK_TEST_PYTHON` to the engine interpreter and run `npm run test:host` for real VS Code
extension-host checks. `VSCODE_EXECUTABLE_PATH` can select an installed Code executable.
Otherwise the runner downloads the pinned test version. Tests use a private generated fixture
workspace and separate VS Code user-data/extension directories.

Project contracts and support boundaries are documented in the repository's local operations
and compatibility references at https://github.com/MipeyV/notebook-to-kedro.

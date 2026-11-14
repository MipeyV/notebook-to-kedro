# ADR 0009: Start with a native VS Code operation interface

[Documentation index](../README.md)

- **Status:** Accepted and implemented as an initial desktop prototype
- **Date:** 2026-11-14

## Context and decision

The user selected VS Code as the first interface after the deterministic local operation
contracts were merged. Provide an Explorer view with explicit configuration/interpreter
selection, diagnostics, read-only file previews and generation with destination confirmation.
Use VS Code's native tree, editor, progress and dialog APIs for the initial workflow.

Keep the extension in `extensions/vscode` in this repository. TypeScript calls the Python
`project` CLI through a selected interpreter with isolated imports, separate process arguments
and bounded responses. The engine retains transformation rules and source accounting.
Validate result schema/status and file-preview transport before presenting it in VS Code.

Refresh the plan before asking for a new generation destination. Generation reads current
saved inputs and retains the existing contained/no-overwrite writer. A canceled confirmation
performs no publication. A preview remains an inspection snapshot, and a future approved-hash
apply contract can build on concrete UI requirements.

## Consequences

- Node build/test dependencies live in the extension package and lockfile. Engine dependencies
  remain defined by the existing Python project.
- The initial release uses explicit interpreter selection and JSON editing. Additional setup
  wizards and automatic environment discovery can follow tested user workflows.
- Package an installable VSIX and exercise real commands through the VS Code extension host
  in a private fixture workspace. Keep UI test execution distinct from ML runtime evidence.
- Project execution, provider calls, remote transport and independent pilot review retain
  their existing contracts. The first interface composes implemented operations.

# Development Journal

This file provides a chronological record of **Notebook to Kedro** development.

It keeps track of:

- work that has actually been completed;
- architectural decisions and their rationale;
- limitations discovered along the way;
- unresolved questions;
- the next concrete step.

This journal is neither a release changelog nor a simple backlog. An entry is added when work is completed or a structural decision is made.

## Entry convention

New entries should follow this structure whenever possible:

```markdown
## YYYY-MM-DD — Short title

### Completed

- ...

### Decisions

- ...

### Open questions

- ...

### Next step

- ...
```

The newest entries are added at the top, immediately below this convention, so the current state remains easy to find.

---

## 2026-08-16 — English adopted as the project language

### Completed

- Translated the project documentation from French to English.
- Kept the MIT license in English.

### Decisions

- English is now the default language for documentation, source code, comments, diagnostics, commit messages, and future project artifacts.

### Open questions

- None for this documentation change.

### Next step

- Initialize the Python package skeleton and specify the first notebook fixtures before implementing the loader.

## 2026-08-16 — Project initialization

### Completed

- Clarified the target problem: automate the transition from a reasonably clean Data Science notebook to a structured Kedro project.
- Defined the initial functional scope and MVP boundaries.
- Proposed a staged architecture: loading, AST analysis, dependency resolution, intermediate representation, Kedro generation, and filesystem writing.
- Identified the primary risks: implicit state, mutations, side effects, Python scopes, parameter inference, and Kedro compatibility.
- Created `README.md` with the project context, goals, scope, and initial roadmap.
- Created this development journal.
- Initialized the local Git repository with `main` as its primary branch.
- Added the open-source MIT license.
- Created and connected the public `MipeyV/notebook-to-kedro` GitHub repository.

### Decisions

- The MVP will not depend on an LLM.
- The intermediate representation will remain separate from the Kedro generator.
- Initially, one convertible code cell will map to at most one task; automatic cell merging is deferred.
- Ambiguous cases must produce explicit diagnostics and may block generation.
- The first implementation milestone will focus on notebook analysis rather than Kedro generation.
- Generated Kedro projects will target an explicitly defined and tested version.

### Open questions

- Choose the minimum supported Python and Kedro versions.
- Define the exact matrix of supported, warned, and rejected constructs.
- Finalize the intermediate representation models.
- Choose a convention for explicit parameter extraction.
- Decide on the final project name and verify its availability before any package publication.

### Next step

- Initialize the Python package skeleton and specify the first notebook fixtures before implementing the loader.

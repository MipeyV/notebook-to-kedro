# Working on Notebook to Kedro

## Start here

- Read [README.md](README.md) and the [documentation index](docs/README.md).
- Check [current status](docs/product/project-status.md), the
  [roadmap](docs/product/roadmap.md) and [architecture](docs/reference/architecture.md)
  before choosing implementation work. Proposed features are not implemented capabilities.
- Stay within the user's requested scope. Existing authorization applies; roadmap entries
  are not instructions to implement every future feature.

## Engineering conventions

- Use English for repository documentation, code, diagnostics and commit messages.
- Keep analysis deterministic and free of notebook execution. Separate source facts,
  semantic proposals, generated artifacts and validation evidence.
- Treat the product as a shared engine composed into operations, with a future local app or
  VS Code interface. Implement concrete working slices; UI must not own transformation rules.
- Preserve [source accounting](docs/reference/source-accounting.md) at the notebook use-case
  boundary. Do not silently omit instructions or replace unsupported reader options. Candidate
  planners and serialized audits alone do not establish source completeness or execution consent.
- Preserve the minimal runtime dependency surface. Kedro, ML libraries and provider SDKs
  must not become analysis dependencies merely to support an integration.
- Keep faithful conversion independently usable. Do not silently optimize or repair source
  logic, weaken AST-fidelity checks, or accept model proposals into normal generation.
- Keep providers replaceable and optional. Current real transports are local Ollama only;
  remote transport and disclosure policies need a separate explicit implementation scope.
- Validate before side effects. Generated projects go through the shared writer, with
  contained nonoverlapping targets and private preparation before publication.
- Tests and synthetic review declarations do not approve the actual pilot. Follow the
  [human review worksheet](docs/evaluation/synthetic-pilot-review.md) and the specific
  provider/execution consent contracts before any live experiment.

## Verification

Use the locked uv environment (`uv sync --locked` when setup is needed). Typical checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv build
```

Start with tests relevant to the change, then run the complete offline suite for changes
to shared conversion contracts. Respect the configured coverage gate. Keep real model calls
and network-dependent experiments outside routine verification; never invent a passing
result for an unavailable interpreter or service.

## Project memory

- Extend existing documents instead of creating competing sources of truth.
- Update affected tests, compatibility claims and reference documentation with code.
- Record significant approved architectural decisions in `docs/decisions/`; index new docs.
- Keep product direction in the vision, priorities in the roadmap, current capabilities in
  status/reference docs, work history in `JOURNAL.md`, and release changes in `CHANGELOG.md`.
- Preserve original corpus/runtime limitations and pending human review in experiment reports.
- The [initial Kedro profiles](docs/guides/kedro-profiles.md) cover one pipeline name and
  function/node prefixes only. Broader standards, greenfield generation and a shared project
  specification remain future work. Do not create empty framework abstractions.

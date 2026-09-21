# Release process

Releases are created from reviewed commits on `main`. Release tags are immutable and use the
package version prefixed with `v`, for example `v0.1.0`.

## Prepare a release

1. Create a `release/X.Y.Z` branch from an up-to-date `main`.
2. Update the version in `pyproject.toml` and `src/notebook_to_kedro/__init__.py`.
3. Move the relevant entries from `Unreleased` into a dated section in `CHANGELOG.md`.
4. Run the local release checks:

   ```bash
   uv sync --locked
   uv run ruff format --check .
   uv run ruff check .
   uv run mypy
   uv run pytest -m "not external and not llm"
   uv build
   ```

5. Open and merge the release pull request after CI succeeds.

## Tag a release

Create the annotated tag only after the release commit is present on `main`:

```bash
git switch main
git pull --ff-only origin main
git tag -a v0.1.0 -m "Notebook to Kedro v0.1.0 - Deterministic MVP"
git show v0.1.0
git push origin v0.1.0
```

Pushing a version tag starts the release workflow. It verifies that the tag matches the package
version, reruns the release checks, builds the wheel and source distribution, and creates a draft
GitHub Release containing both artifacts.

## Publish the GitHub Release

Review the generated draft before publishing it:

1. set the title to `v0.1.0 - Deterministic MVP`;
2. use the matching `CHANGELOG.md` section as the release notes;
3. confirm that the wheel and source distribution are attached;
4. mark `0.x` releases as pre-releases while the public API remains unstable;
5. publish the release.

Do not move or recreate a published tag. Create a patch release when a released artifact needs a
correction.

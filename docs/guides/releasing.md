# Release process

[Documentation index](../README.md)

Releases are created from reviewed commits on `main`. Release tags are immutable and use the
engine version prefixed with `v`, for example `v0.2.0`. Engine and extension versions are
independent: the 0.2.0 engine is paired with VS Code extension 0.4.0. The release manifest
records both versions and the exact source commit. This is a preview with an evolving API;
the supported source/runtime boundaries still apply.

## Prepare a release

1. Create a `release/X.Y.Z` branch from an up-to-date `main`.
2. Update the version in `pyproject.toml` and `src/notebook_to_kedro/__init__.py`, then run
   `uv lock --offline` to update the root package entry without upgrading dependencies.
   If the extension changes, update its package.json and package-lock.json versions together.
3. Move implemented entries from `Unreleased` into a dated section in `CHANGELOG.md`. Include
   a concise `### Release overview` with the paired versions, installation and limitations.
   The bundle tool derives GitHub release notes from this overview, leaving detailed history intact.
4. Run the local release checks:

   ```bash
   uv sync --locked
   uv run ruff format --check .
   uv run ruff check .
   uv run mypy
   uv run pytest -m "not external and not llm"
   uv build --no-build-isolation --python .venv/bin/python --out-dir generated/release-dist-0.2.0
   cd extensions/vscode
   npm ci --no-audit --no-fund
   npm run format:check
   npm test
   npm run package
   ```

   On Windows use `.venv/Scripts/python.exe` and `npm.cmd`. Return to the repository root
   before preparing the local bundle:

   ```bash
   uv run python tools/prepare_release.py --artifacts generated/release-dist-0.2.0 --vsix generated/notebook-to-kedro-0.4.0.vsix --output generated/release-review-0.2.0 --commit "$(git rev-parse HEAD)"
   ```

   Use a fresh build directory containing only the expected wheel/source archive, and a new
   bundle destination under `generated/`. The tool refuses version/lock mismatches, changed
   wheel/source/VSIX contents, stale artifact names and existing bundle destinations. It uses
   the shared staging writer and verifies copied checksums. It creates no tag or GitHub Release.
   The standard uv `*` `.gitignore` build marker is ignored and is never a release asset.

5. Open and merge the release pull request after CI succeeds. The quality job installs the
   actual wheel in a separate core-only environment and runs its CLI from outside the checkout.
   It also builds/verifies the paired VSIX and uploads `notebook-to-kedro-release-preview` as
   a reviewable six-file bundle. CI artifacts are temporary review outputs, not published releases.

## Tag a release

Create the annotated tag only after the release commit is present on `main`:

```bash
git switch main
git pull --ff-only origin main
git tag -a v0.2.0 -m "Notebook to Kedro v0.2.0 - Local engineering preview"
git show v0.2.0
git push origin v0.2.0
```

Pushing a version tag starts the release workflow. It requires main ancestry and matching engine
version, reruns the locked Python/extension tests and both actual VS Code host modes, and builds
the engine/VSIX pair. The installed engine smoke check uses only core dependencies. The bundle
tool verifies source/compiled bytes and metadata before the workflow creates a **draft** Release.
The tag workflow rebuilds from the tagged commit; it does not republish a PR artifact or create
tags implicitly. The source commit is declared by the trusted workflow; the manifest is not a
cryptographic source attestation.

Every bundle includes:

- `notebook_to_kedro-0.2.0-py3-none-any.whl` and `notebook_to_kedro-0.2.0.tar.gz`;
- `notebook-to-kedro-0.4.0.vsix`;
- `release-manifest.json`, pairing versions/source commit and artifact sizes/hashes;
- `RELEASE_NOTES.md` from the dated changelog overview;
- `SHA256SUMS` for the three packages, manifest and notes (not for itself).

The examples above use the current versions; use the matching metadata on later release branches.
The bundle cannot establish scientific acceptance, runtime equivalence of arbitrary projects,
pilot review or environment locking for generated ML projects.

## Publish the GitHub Release

Review the generated draft before publishing it:

1. check the generated title, changelog-derived notes and tested engine/extension pair;
2. confirm that all six assets are attached and their checksums match (`sha256sum -c SHA256SUMS`
   from the downloaded asset directory; the equivalent Windows check is `Get-FileHash`);
3. check the installation instructions and known supported-subset/validation limits;
4. keep `0.x` releases marked as pre-releases (the workflow sets this flag automatically);
5. publish the release.

Do not move or recreate a published tag. Create a patch release when a released artifact needs a
correction.

There is no automatic public publication, PyPI upload or VS Code Marketplace publication.

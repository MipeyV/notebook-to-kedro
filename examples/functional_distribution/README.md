# Synthetic application distribution

This trusted fixture reads its installed distribution version, a packaged resource
and a project-relative auxiliary file. `application.lock` is a synthetic identity
fixture. Its contents provide a stable byte-hash check.

The root-level `workflow.json` selects static distribution capture and JSON I/O.
Generate from `src/distribution_ml/workflow.py` with the repository root as the
project root. Follow the generated README to install the two local projects.

The wheel probe covers installed metadata and packaged resources. Editable
installation also exposes the project-relative auxiliary file to the application.

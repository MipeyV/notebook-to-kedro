# Prepared coding-agent comparison inputs

The data-only corpus.json freezes three synthetic tasks, original source/configuration/oracles,
explicit acceptance requirements and portable one-prompt templates from the 2026-11-17 experiment.
observations.json records aggregate outcomes, timing boundaries and limitations. Detailed local
projects/logs and the experiment-specific coordinator checker are not product APIs or included here.

Extract a case into a NEW directory under ignored generated/ using the shared writer:

```python
import json
from pathlib import Path
from notebook_to_kedro.generation.writer import write_project

repo = Path.cwd().resolve()
corpus = json.loads((repo / "examples/agent_comparison/corpus.json").read_text(encoding="utf-8"))
case = corpus["cases"][0]  # choose a case; preserve its input strings verbatim
target = repo / "generated/expanded-agent-comparison-v1" / case["case_id"]
files = {Path(name): text for name, text in case["files"].items()}
files[Path("prompt-template.txt")] = files[Path("prompt-template.txt")].replace(
    "${REPOSITORY_ROOT}", repo.as_posix()
)
write_project(target, files)  # refuses an existing directory
```

The frozen templates refer to this experiment's target layout; choose a new isolated layout and
update only those path references for a repeat. Use the locked development environment and its
actual Python path. Source/specification reading, configuration authoring and environment setup
were not timed in the original converter lane. Running or reusing these data grants no independent
human review or live pilot approval. See ../../docs/experiments/prepared-agent-comparison.md.

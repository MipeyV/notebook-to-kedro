# Draft notebook Ollama controls

[Documentation index](../README.md)

Status: **metadata-only Python API implemented; actual pilot review and live campaign pending**.
Version: `notebook-ollama-controls-draft-1`. This is separate from notebook source bindings,
execution ledgers and historical node benchmark artifacts. None of those formats is migrated.
No installed model was selected, queried, downloaded or invoked for this increment's tests.

## Requested, advertised and effective

| Layer | Recorded evidence | Interpretation |
| --- | --- | --- |
| Requested | `NotebookOllamaSettings`: `temperature`, optional `seed`, `num_ctx`, `num_predict`. | Caller intent only; collection does not apply these options to any endpoint. Unspecified options stay omitted in `to_options()`. |
| Advertised | Opaque `parameters` text and architecture-specific model context capacity from the recorded show response. | Server-reported model metadata, not a measured runner configuration. Missing fields stay null. |
| Effective | `effective_options` and `effective_context_length` are always null. | This metadata-only API cannot certify options applied to a future inference. |

Requested temperature must be finite/nonnegative; seed must be a nonnegative integer. Explicit
context and prediction budgets must be positive integers, not booleans or unbounded sentinel
values. These are selected controls, not the complete chat request: prompts, schema, streaming,
thinking flags and provider implementation still need binding in the future campaign envelope.
No existing provider is reconfigured by creating or loading this record.

## Collection boundary

`collect_notebook_ollama_controls` requires `allow_local_metadata_queries=True` before any I/O.
It makes exactly these five requests on the successful path, with no retry:

1. `GET /api/version` (`version_before`).
2. `GET /api/tags` (`tags_before`).
3. `POST /api/show` (`show`), with only `model` and `verbose: false` in the body.
4. `GET /api/version` (`version_after`).
5. `GET /api/tags` (`tags_after`).

It sends no notebook, prompt, generation options or credentials. It never calls chat, generate,
embedding, pull, model lifecycle or worker endpoints. Model names are matched exactly against
the inventory; there is no implicit tag expansion, model selection, fallback or download.
Cloud-style names, reported remote mappings, disagreeing aliases and duplicate selected entries
are refused. Remote evidence detected before show stops collection before that POST.
Known `remote_host`/`remote_model` markers are checked in every response and selected model row,
including offline reconstruction. Non-empty or ambiguous values are refused; unrelated model
inventory is retained without being treated as the selected model's configuration.

The new collector accepts only the existing local HTTP origins. It canonicalizes `localhost`
to literal `127.0.0.1`, accepts literal `::1`, bypasses environment HTTP proxies and refuses all
HTTP redirects. These transport guards apply to this collector, not retroactively to existing
providers or the older node-provenance HTTP helper. The version/digest decoder is shared with
the latter while preserving its historical behavior and artifact formats.

Default timeout is five seconds per request and default raw response bound is 1,000,000 bytes.
Timeouts are socket/request limits, not a hard total wall-clock deadline. Transport errors,
invalid UTF-8/JSON, duplicate keys, non-finite constants, malformed required shapes and explicit
server error responses abort collection. There is no automatic partial HTTP capture, retry or
inference-attempt registration; callers explicitly publish only a completed metadata sample.

The endpoint roles and metadata fields follow the official
[Ollama API description](https://github.com/ollama/ollama/blob/main/docs/api.md) and
[request/response definitions](https://github.com/ollama/ollama/blob/main/api/types.go), checked
on 2026-10-23. API evolution does not authorize automatic schema reinterpretation.

## Offline evidence and compatibility

`create_notebook_ollama_controls` reconstructs a sample from five ordered
`NotebookOllamaResponse` values without any HTTP. Exact raw UTF-8 JSON strings are retained,
including unrelated installed-model inventory. Canonical hashes bind each selected target row
and the complete show object. A content hash binds the full record and derived summaries.

Absent versions/digests remain null. Observed before/after identity drift remains inspectable.
`require_notebook_ollama_compatibility(before, after, current)` refuses unknown version/digest
identities, within-sample drift, changed endpoints/model names/requested options, selected target
rows or show metadata across samples. It ignores unrelated model inventory and JSON whitespace
when comparing selected controls; those bytes still affect each full record's content hash.

If `num_ctx` is explicitly requested, compatibility also requires a known advertised capacity
at least that large. Without an explicit context request, absent advertised context does not
block this **identity-only** gate. Passing it never proves an effective context or temperature,
determinism, supported inference capability, complete runtime compatibility or campaign readiness.

`write_notebook_ollama_controls` publishes exclusively and never overwrites existing evidence.
`load_notebook_ollama_controls` bounds file reads, checks exact shapes and reconstructs every
derived summary from the saved responses without contacting a service. Rehashing a forged
summary or changing effective nulls does not bypass reconstruction. The default whole-record
bound is 32 MiB; structured-object decoding has no additional serialized-size limit.

```python
from notebook_to_kedro.evaluation import (
    NotebookOllamaSettings,
    collect_notebook_ollama_controls,
    load_notebook_ollama_controls,
    write_notebook_ollama_controls,
)

sample = collect_notebook_ollama_controls(
    "your-installed-model:tag",
    allow_local_metadata_queries=True,
    requested=NotebookOllamaSettings(temperature=0, num_ctx=4096, num_predict=1024),
)
write_notebook_ollama_controls("generated/pilot-model-controls.json", sample)
inspected = load_notebook_ollama_controls("generated/pilot-model-controls.json")
assert inspected.effective_context_length is None
```

Metadata may contain model names, paths, templates, system messages, licenses or sensitive
configuration. Store it privately; ignored `generated/` destinations are examples, not access
controls or encryption. No redaction, authenticated storage or cloud-secret handling is added.

## Limits and next gate

The sample is a server advertisement, not authentication of Ollama, model blob bytes, hardware
or loaded binaries. Hashes do not prevent a same-user adversary from forging all evidence.
Sampling is not a lock; reverted changes between samples can escape detection. Show is observed
at one point between tag/version samples, not in an atomic server transaction. The collector
cannot prove that a local server itself never proxies traffic or lies about remote metadata.
Operator isolation, actual server configuration and privacy controls remain necessary.

Tests use synthetic metadata and fake HTTP openers only. Actual independent human review of the
[pilot](synthetic-pilot-review.md) remains pending. An [offline campaign envelope](notebook-campaign-preflight.md)
now binds a supplied reviewed reference and model sample to exact proposed requests, budgets and
all-slot capture accounting. Next: actual review, operator-selected samples and consent-gated
dispatch linked to [all registered execution attempts](notebook-execution-ledger.md). The existing
execution ledger does not yet consume these model controls or send model requests.
No whole-notebook model calls are authorized by this increment.

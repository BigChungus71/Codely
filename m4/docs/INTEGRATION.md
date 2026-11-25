# M2 and M3 integration

## Current team branch compatibility

M3's security scan and M2's finding schema use `file` and a `cwe` array. The M4 adapter accepts that finding shape, validates source ranges, and preserves finding ID, rule ID, severity, message and CWE identifiers. M4's standalone `path` and optional string `cwe` shape still works.

Call `review_for_m2(index, finding, provider)` to return the exact M2 `Explanation` fields used by the frontend client. The response always requires developer review. A single grounded edit can populate `suggested_code`. Use `review_normalized` for M4's richer internal result with citations, root cause and the full diff. The existing M2 DTO exposes a smaller public shape.

M2's `CODELY_EXPLANATION_ADAPTER` hook accepts `(finding, context)` with a bounded excerpt. The excerpt carries no authorized checkout root or project ID. Bind the adapter to an already authorized snapshot if the deployment has one configured immutable project. For multiple projects, use the route's authenticated project and revision to resolve the snapshot in M2 before invoking M4. M2 owns that binding and cache. The adapter can then be called synchronously by M2's current synchronous route or passed to a worker by an async route.

## FastAPI worker boundary

Keep the synchronous indexing, embedding, and review calls off FastAPI's event loop. M2 owns authorization, checkout lifetime, and the worker pool; the package does not create an API server or persist project data.

```python
from fastapi.concurrency import run_in_threadpool
from ai_intelligence.integration import review_for_m2

async def review_for_project(index, normalized_finding, provider):
    return await run_in_threadpool(review_for_m2, index, normalized_finding, provider)
```

Validate request data with the contracts before calling the worker. Map invalid findings and unavailable source ranges to client errors, and provider failures to an upstream-service error while preserving the original scanner result separately. Do not log API keys, request headers, source excerpts, prompts, model output, or complete scanner findings; return only data authorized for the caller. Provider errors intentionally omit response bodies and credentials.

## M2 backend

Make `m4/` importable in the M2 Python environment and install the relevant M4 requirements. Build the index in a worker using a private, immutable, already extracted repository checkout. Cache it by authorized tenant, project ID, and revision. Enforce that authorization in M2 and expire indexes when the project or revision expires. The package owns an in-memory index per instance. Avoid passing a live, concurrently writable checkout.

```python
from pathlib import Path

from ai_intelligence.context import RepositoryContext
from ai_intelligence.embeddings import LocalEmbedder
from ai_intelligence.integration import review_normalized
from ai_intelligence.providers import create_generator

provider = create_generator()
embedder = LocalEmbedder(Path("/models/all-MiniLM-L6-v2"))
index = RepositoryContext("project-id", Path("/private/checkout"), embedder=embedder)

result = review_normalized(index, normalized_item, provider)
```

Initialize the selected provider once per worker or application lifespan. For Groq, call `provider.close()` at shutdown after in-flight work finishes. Select a live provider only for requests whose repository is approved for external processing. Consumers of the richer M4 contract that enumerate `mode` values should also accept `groq`.

Preserve normalized scanner results before calling this package. An evidence range that is missing, filtered, or outside the snapshot raises `ContextError`. Provider failures and ungrounded citations raise `ProviderError`. Invalid payloads raise Pydantic `ValidationError`. Return scanner results when AI review is unavailable and display the error separately. The CLI accepts both normalized arrays and local Semgrep JSON and gives each source range its own review or failure entry.

Redaction is heuristic. The index filters hidden, generated and dependency paths and common credential filenames, rejects private-key blocks and masks recognized secret-like assignments and token formats. M2 owns checkout and upload policy. Do not show stored scanner messages or repository text to unauthorized users. Raw scanner data is preserved in output, so avoid persisting it in shared logs. Display code, model text and diffs as escaped data in the frontend.

## M3 static findings

Use one-based, inclusive scanner line numbers and canonical repository-relative POSIX paths. Use the stable ID and severity assigned by M3. The local Semgrep adapter hashes rule, path and location for standalone demos. Its IDs can change when a finding moves.

Example normalized scanner input for a synthetic fixture:

```json
[
  {
    "id": "fixture-1",
    "rule_id": "fixture.unsafe-eval",
    "severity": "ERROR",
    "path": "app.py",
    "start_line": 4,
    "end_line": 4,
    "message": "Review dynamic evaluation in the numeric parser.",
    "cwe": "CWE-95"
  }
]
```

Example response excerpt:

```json
{
  "finding_id": "fixture-1",
  "mode": "mock",
  "source_evidence": [
    {
      "id": "app.py:4-4",
      "path": "app.py",
      "start_line": 4,
      "end_line": 4,
      "text": "    return eval(value)",
      "reason": "affected",
      "similarity": null,
      "redacted": false
    }
  ],
  "affected_files": [],
  "edits": [],
  "proposed_diff": ""
}
```

The full review also contains `scanner_finding` and `interpretation`, including assumptions, impact, prerequisites, contextual concerns and verification steps. Quote references by evidence ID. Semantic scores express cosine similarity. Structural candidates and semantic scores require source inspection before drawing conclusions about dependencies.

For verification, M2/M3 can apply the reviewed `proposed_diff` to a disposable checkout of the same revision, using a patch check first. The produced patch has zero context, so a Git-based worker uses `git apply --check --unidiff-zero` before applying and verifies the supplied original ranges against that revision. Treat rejected or stale patches as review failures. Run the same M3 scanner and ruleset before and after, and record results independently. Keep all application execution and testing decisions in the team verification worker.

## M3 architecture graph

Pass a selected observed subgraph to `architecture.advise(index, graph, requirements, provider)`. Both nodes and edges require small source ranges so recommendations can cite actual evidence.

```json
{
  "nodes": [
    {"id": "web", "label": "Controller", "location": {"path": "src/Controller.java", "start_line": 8, "end_line": 8}},
    {"id": "service", "label": "Service", "location": {"path": "src/Service.java", "start_line": 12, "end_line": 12}}
  ],
  "edges": [
    {"id": "web-service", "source": "web", "target": "service", "label": "calls",
     "location": {"path": "src/Controller.java", "start_line": 23, "end_line": 23}}
  ]
}
```

`architecture.advise` accepts Groq, Gemini, or an architecture-specific fixture provider. The generic `MockGenerator` implements review only. Observed nodes and edges are returned as supplied. Proposed edges have React Flow's `id`, `source` and `target`. Map proposed nodes to `{id, data: {label}, position}` in the frontend layout. For graph scope, pass up to 15 nodes and 20 edges with short evidence ranges. A proposal may reference observed or proposed nodes. Treat all proposed graph changes as suggestions.

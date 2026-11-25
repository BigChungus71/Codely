# Architecture dependency graph v1.0.0

Phase 5 consumes Phase 4's RepositoryStructure and the existing NetworkX 3.6.1
dependency. It never opens target files, reparses source, invokes a scanner,
imports target modules, calls an API or uses an LLM. No frontend component or
complete vulnerability impact mapper is implemented.

## Public interface

```python
from backend.app.analyzers.structure_analyzer import analyze_repository
from backend.app.analyzers.architecture_graph import build_architecture_graph, GraphOptions
from backend.app.analyzers.architecture_traversal import TraversalLimits

structure = analyze_repository(validated_repository_path)  # reuse this if already available
architecture = build_architecture_graph(structure)
payload = architecture.to_dict()
```

Use `app.analyzers...` when running from backend/. The builder requires a trusted
RepositoryStructure object, not a repository path or arbitrary JSON. It does not
mutate that object. GraphOptions sets positive max_nodes (10,000), max_edges
(100,000), and max_evidence_records (200,000) budgets. Truncation/invalid evidence
produces diagnostics and partial status instead of dangling edges. Existing
scanner, checklist, AST and shared architecture required fields are unchanged.

`architecture.networkx_graph` returns a detached frozen DiGraph copy. Mutating its
attributes does not change the engine's internal graph. Use `.to_dict()` for a
detached presentation payload rather than changing in-memory result lists.

## Nodes, roles and evidence

One node represents one observed Python module/file, including package initializers
and unparsed file-backed modules. Modules and files are not duplicated into parallel
nodes. Source module IDs are reused. External packages, stdlib namespaces, unknown
imports and namespace directories without a Python source file do not create nodes.

Required node fields remain `id`, `label`, `type`, `file`. Optional fields include
parsed, module_names, classification_confidence, classifications, fan_in and fan_out.
Classifications retain source file/lines, confidence and reason from Phase 4:

- application_entry_point (explicit API application constructor indicator)
- router or controller/route handler
- service
- data_access (repository/data-access role)
- database_model (recognized framework model-base indicator)
- authentication
- configuration
- utility
- test
- unclassified

Confirmed means explicit **static evidence**, not effective deployment, route
protection, a mapped table, or runtime behavior. Services and other filename-based
roles retain inferred confidence. If no role exists, conventional main/app/asgi/
wsgi/__main__ filenames can supply an explicitly inferred entry-point indicator.
Other modules remain unclassified. The primary type is a deterministic display
choice: confirmed before inferred, then the order listed above. All selected
classification evidence remains available; this choice does not enforce layers or
assert a unique module responsibility. No role is inferred from fan-in/out metrics.

## Edge direction and aggregation

**Importing module -> Imported module.** If controller imports service and service
imports repository, the graph is `controller -> service -> repository`.

Required edge fields remain `source`, `target`, `relationship` (`imports` here).
Optional `id` hashes endpoint IDs and relationship. A DiGraph stores one edge per
ordered module pair. Its evidence array preserves every distinct supporting import:
import_id, relative source file, start/end lines, internal resolution, conditional
flag, scope_id when available, and target_parsed. Multiple from-import members or
statements share a pair without losing evidence. Exact duplicate records are
removed and counted. The builder verifies evidence against a unique resolved import
and existing endpoint modules; inconsistent, unresolved or dangling records cannot
invent edges. Conflicting records are rejected/reported deterministically.

These are direct observed static imports, including function-local/conditional
imports. They do not prove that execution reaches either module. Implicit parent
package effects, runtime hooks, unknown re-exports, dynamic imports and calls are
not fabricated as relationships. See STRUCTURE_INTEGRATION.md for resolution limits.

Node/edge ordering is deterministic. Edges are ordered by endpoint ID; evidence
ordering is stable by import ID. Component IDs hash sorted membership. Edge IDs
survive additional statements between the same files; evidence import IDs retain
Phase 4's coordinate-dependent identity. No source literals are added to the graph.

## Graph intelligence

Statistics include node/edge/evidence counts, unique-neighbor fan-in/out, weakly
connected component summaries, every strongly connected component, observed isolated
modules, self-import count and cyclic components. A component is cyclic when it has
more than one member or a self-import. Each cyclic component contains one valid,
deterministically selected cycle witness with node/edge IDs. This detects cycle
presence without an unbounded enumeration of all simple cycles. WCC membership
ignores direction only for grouping; dependency edges never reverse orientation.

Self-imports contribute one to both fan-in and fan-out. Multiple import statements
on the same pair do not inflate fan metrics; evidence_count records those statements.
Isolation means no **observed internal edge**, not unused code. Unknown/unparsed
modules and omitted external dependencies can materially limit these metrics.
No metric or cycle result alone is an architectural quality or security verdict.

## Traversal helpers and Phase 6 preparation

```python
module = architecture.module_for_file("src/demo/services.py")
if module is not None:
    module_id = module["id"]
    outgoing = architecture.direct_dependencies(module_id)
    incoming = architecture.direct_dependents(module_id)
    downstream = architecture.transitive_dependencies(module_id)
    upstream = architecture.reverse_dependencies(
        module_id, limits=TraversalLimits(max_depth=4, max_nodes=100, max_edges=1000, max_paths=50)
    )
    paths_payload = upstream.to_dict()
```

Module lookup is indexed, requires a relative path, accepts Windows separators,
and returns None for missing files. Escaping/absolute/UNC/drive-relative paths
are rejected. Match the repository's path case. Neighbor methods return sorted
IDs; unknown IDs raise KeyError. Transitive traversals return nodes ordered by
shortest distance then ID, excluding the seed even in a cycle. Direct neighbor
methods can include a self-import. BFS visits a node once and handles cycles safely.

Defaults: depth 32 (configurable 0..256), 1,000 visited nodes **including the seed**,
10,000 examined edges, and 128 returned paths. Budgets are explicit and positive,
except depth can be zero. One deterministic shortest path is returned per included
module, not all possible paths. Equal-distance choices follow sorted node IDs.

Incoming traversal walks against the arrows to find importing modules, but its
returned paths always follow actual import direction. From repository R, an upstream
path to controller C is `[C, service, R]`, not a claim that R imports C. A path's
target_id identifies the reached module C even though R is the final arrow endpoint.
edge_ids refer to the traversal's de-duplicated evidence_edges list, which contains
the original merged import evidence. This avoids copying large evidence arrays
into every overlapping path.

`truncated`, `limit_reasons`, examined_edges, visited_nodes and limits disclose
bounded exploration. max_paths can truncate returned paths while reached nodes
are still available. `coverage_status` carries graph status; truncated=false never
overrides partial source coverage. These generic helpers support future potentially
affected-upstream analysis, but no finding/severity mapping, exploitability estimate,
affected-component verdict or complete Phase 6 engine is included.

## Contract and frontend use

`contracts/architecture-graph-v1.schema.json` validates both the shared minimum
nodes/edges shape and this richer v1 payload. Optional root fields are schema_version,
status, statistics, diagnostics and coverage. Node IDs are unique and every edge
endpoint exists. The example `contracts/examples/architecture-graph-v1.json` is
generated from the existing structure fixture, not invented UI data.

React Flow needs presentation positions and registered renderer types. Keep semantic
architecture roles in data and let the frontend own layout/rendering:

```typescript
const nodes = payload.nodes.map(n => ({
  id: n.id, type: "default",
  data: { label: n.label, componentType: n.type, file: n.file, classifications: n.classifications },
  position: positions[n.id] ?? { x: 0, y: 0 },
}));
const edges = payload.edges.map(e => ({
  id: e.id, source: e.source, target: e.target,
  data: { relationship: e.relationship, evidence: e.evidence },
}));
```

Do not register arbitrary semantic role strings as renderer names unless corresponding
components exist. This mapping is documentation only; no React code was changed.
Show partial/error coverage and inferred role styling; do not label the picture as
a verified runtime call graph or complete dependency inventory.

The teammate backend's inspected Graph model accepts required nodes/edges, but
currently drops these extra fields and does not reject partial graphs. A backend
owner must explicitly check status and preserve optional metadata before publishing
the richer payload. Its CODELY_ARCHITECTURE_ADAPTER hook takes a path, whereas the
pure builder takes a structure object: a worker adapter must obtain/reuse structure,
build once, and decide how to handle partial coverage. Do not point that hook
directly at build_architecture_graph. No teammate API/schema/adapter was modified.

## Verification and commands

```powershell
# Convenience command: one AST analysis followed by one graph build.
python -m backend.app.analyzers.architecture_cli fixtures/structure_demo
python -m pytest backend/tests/test_architecture_graph.py -q
$env:CODELY_RUN_SEMGREP_INTEGRATION = "1"
python -m pytest -q
```

CLI exit 0 means complete build within the available structure scope; exit 2
means partial/error. Unresolved imports remain counted even with complete file
extraction. The intentionally malformed fixture exits 2 with usable graph JSON.
Graph limits and source gaps remain explicit. Empty graphs serialize safely;
invalid/empty repository status from Phase 4 is not changed to complete.

Actual results on Windows/Python 3.11.9/NetworkX 3.6.1: 71 new graph tests pass.
Full regression: 281 passed (262 unit/static, including those 71, plus all 19 real
native Semgrep/checklist tests). The new tests include synthetic graph structures,
actual AST-backed fixture/multilayer graphs, schema/example checks, deterministic
shortest paths, conflicts, Windows paths, privacy, budget truncation, a 1,000-module
chain and a 1,100-module cycle. No target source was executed.

Representative fixture: 13 nodes, 7 edges, 7 import evidence records, 12 SCCs,
one cyclic component, seven weak components, six observed isolated modules,
max fan-in 4, max fan-out 2. Status is partial due to the deliberate syntax error.
An actual graph of the shared checkout has 86 nodes, 51 merged edges, 81 import
evidence records and one cyclic component; its partial result is saved locally
in ignored `.semgrep-local/phase5-shared-graph.json`. These are observations, not
architecture quality conclusions. No new dependencies or prior contracts changed.

Phase 6 now consumes this unchanged graph through
`impact_analyzer.analyze_security_impact(scan, structure, architecture)`.
See IMPACT_INTEGRATION.md for potential-relevance semantics and coverage limits.

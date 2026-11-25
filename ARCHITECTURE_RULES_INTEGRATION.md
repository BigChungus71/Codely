# Architecture Rules and Optimization Engine v1.0.0

Phase 7 consumes Phase 4's `RepositoryStructure` and Phase 5's `ArchitectureGraph`
to emit deterministic structural observations, requirement-aware policy checks,
advisory refactoring recommendations, and a structured evidence package for Gemini.
It never re-reads target files, reparses source, invokes a scanner, executes target
code, rewrites source files, or calls an LLM.

Phase 6 was verified at local/remote commit `3a87132` with a clean working tree and
342 passing tests. Phase 7 is additive and preserves all existing scanner, checklist,
AST, graph, ASIM, contract, and CodeRAG provenance hashes.

## Public interface and reuse

```python
from backend.app.analyzers.structure_analyzer import analyze_repository
from backend.app.analyzers.architecture_graph import build_architecture_graph
from backend.app.analyzers.architecture_rules import (
    ArchitectureEvaluationOptions,
    ArchitecturePolicy,
    ArchitectureThresholds,
    LayerPolicy,
    evaluate_architecture,
    load_policy,
)

structure = analyze_repository(validated_repository_path)
architecture = build_architecture_graph(structure)

# Option A: general structural & heuristic evaluation (no layer assumptions)
observations = evaluate_architecture(structure, architecture)

# Option B: requirement-aware evaluation with a configured policy or JSON file
policy = load_policy("contracts/examples/architecture-policy-v1.json")
observations = evaluate_architecture(structure, architecture, policy=policy)

payload = observations.to_dict()
gemini_evidence = observations.gemini_evidence_package()
single_evidence = observations.gemini_evidence_package(observation_id=payload["observations"][0]["id"])
```

When running from `backend/`, import `app.analyzers.architecture_rules` instead.
Reuse existing `RepositoryStructure` and `ArchitectureGraph` instances from the
same immutable repository version; `evaluate_architecture` verifies module/edge
consistency and fails closed (`status="error"`, `graph_structure_mismatch`) if inputs
do not match.

## Implemented rules

| Rule ID | Category | Evidence classification | Scope and false-positive guards |
| --- | --- | --- | --- |
| `CODELY-ARCH-001` | `dependency_cycle` | `confirmed_structural` | Strongly connected components with >1 module or self-import; distinguishes conditional/function-local cycles as `MEDIUM` |
| `CODELY-ARCH-002` | `layer_boundary` | `confirmed_structural` / `heuristic_maintainability` | Only active when explicit `layers` policy is configured; skips `unclassified` and `test` modules by default |
| `CODELY-ARCH-003` | `layer_boundary` | `confirmed_structural` / `heuristic_maintainability` | Direct `controller` / `router` -> `data_access` dependencies where prohibited by configured policy; inactive when `policy=None` |
| `CODELY-ARCH-004` | `coupling` | `heuristic_maintainability` | `fan_in + fan_out > max_total_coupling` (default `12`); excludes `test` modules by default |
| `CODELY-ARCH-005` | `coupling` | `heuristic_maintainability` | `fan_in > max_fan_in` (default `8`); shared `utility`/`configuration`/`database_model`/package modules default to `LOW` advisory priority |
| `CODELY-ARCH-006` | `coupling` | `heuristic_maintainability` | `fan_out > max_fan_out` (default `8`); `application_entry_point` composition roots default to `LOW` advisory priority |
| `CODELY-ARCH-007` | `size_complexity` | `heuristic_maintainability` | Parsed module lines (`400`), functions (`15`), or classes (`8`) exceeding configured thresholds |
| `CODELY-ARCH-008` | `size_complexity` | `heuristic_maintainability` | Function/method line span exceeding `max_function_lines` (default `60`) |
| `CODELY-ARCH-009` | `size_complexity` | `heuristic_maintainability` | Effective parameter count exceeding `max_function_parameters` (default `6`; excludes leading `self`/`cls` on non-static methods) |
| `CODELY-ARCH-010` | `inheritance` | `confirmed_structural` / `heuristic_maintainability` | Class inheritance depth exceeding `max_inheritance_depth` (default `3`), resolving intra-file and static internal imports safely across cycles |
| `CODELY-ARCH-011` | `responsibility_concentration` | `heuristic_maintainability` | >=`max_responsibility_groups_per_module` (default `3`, grouping transport roles together and persistence roles together) or class methods > `max_class_methods` (default `15`) |
| `CODELY-ARCH-012` | `dependency_integrity` | `confirmed_structural` | Unresolved local/relative/attribute imports or ambiguous multi-candidate internal imports; excludes unknown external packages (`not_local_stdlib_or_known_external`) |

## Requirement-aware policy and schemas

- Policy schema: `contracts/architecture-policy-v1.schema.json`
- Example policy: `contracts/examples/architecture-policy-v1.json`
- Evaluation schema: `contracts/architecture-evaluation-v1.schema.json`
- Representative example output: `contracts/examples/architecture-evaluation-v1.json`

When `policy=None`, the engine does **not** assume layered architecture, microservices,
or any specific design pattern; layer boundary rules (`CODELY-ARCH-002` and
`CODELY-ARCH-003`) stay inactive and only general structural checks and configurable
heuristics run. Isolated modules (`fan_in == 0, fan_out == 0`) are never flagged as defects.

## Frontend integration

Keep architecture observations completely separate from security vulnerability findings:

- Do not map `priority` (`HIGH` / `MEDIUM` / `LOW`) or `rule_id` into the security
  findings table, CVSS/CWE panels, or vulnerability counts.
- Render `evidence_classification` (`confirmed_structural` vs `heuristic_maintainability`),
  `confidence` (`confirmed`, `inferred`, `heuristic`), and `advisory_only: true` clearly
  so users review heuristics in context rather than treating every metric as a defect.
- Highlight existing architecture graph nodes and edges using
  `supporting_graph_evidence.node_ids`, `supporting_graph_evidence.edge_ids`, and
  `supporting_graph_evidence.dependency_paths` without rebuilding the graph.
- Surface `status` (`complete` / `partial` / `error`), `coverage.unparsed_modules`,
  `coverage.unresolved_internal_imports`, and `coverage.truncated` whenever evaluation
  coverage is incomplete.

## Gemini integration

Call `observations.gemini_evidence_package()` (repository-wide) or
`observations.gemini_evidence_package(observation_id)` (single observation) to pass
structured, deterministic evidence to the GenAI layer:

- Includes: `user_constraints`, `supporting_metrics`, `observations` (with observed
  metrics, thresholds, deterministic suggestions, trade-offs, validation methods, and
  limitations), `relevant_modules`, `relevant_symbols`, `relevant_edges`,
  `dependency_paths`, `analysis_limitations`, and `interpretation_guidance`.
- Excludes: literal values, assignment values, call arguments, docstrings, source code
  snippets, raw scanner messages, security vulnerability findings, exploitability
  probabilities, runtime performance claims, and overall architecture quality scores.
- If the GenAI layer requires source excerpts for contextual refactoring prose, the
  backend/GenAI owner must retrieve narrowly authorized, redacted spans for
  `source_locations` via its own source-access boundary.

## CLI and verification

```powershell
# Evaluate with default heuristics (no layer policy assumed)
python -m backend.app.analyzers.architecture_rules_cli fixtures/impact_demo

# Evaluate with an explicit JSON policy and emit raw evaluation JSON
python -m backend.app.analyzers.architecture_rules_cli fixtures/architecture_rules_demo --policy contracts/examples/architecture-policy-v1.json

# Emit the structured Gemini evidence package
python -m backend.app.analyzers.architecture_rules_cli fixtures/architecture_rules_demo --policy contracts/examples/architecture-policy-v1.json --gemini-package

# Run Phase 7 unit & contract tests
python -m pytest backend/tests/test_architecture_rules.py -q
```

CLI exit `0` indicates `status == "complete"`; exit `2` indicates `partial` or `error`
(for example when unparsed files, unresolved internal imports, or empty repositories occur).

## Demonstration results (`fixtures/architecture_rules_demo`)

Evaluated with `contracts/examples/architecture-policy-v1.json` (8 modules, 5 internal
edges, 6 classes, 8 functions; saved in `contracts/examples/architecture-evaluation-v1.json`):

- `status`: `partial` (due to deliberate unresolved internal import in `broken_imports.py`)
- `total_observations`: `5` (`3 HIGH`, `1 MEDIUM`, `1 LOW`; `4 confirmed_structural`, `1 heuristic_maintainability`)
  - `CODELY-ARCH-001`: circular dependency between `billing_service.py` and `order_service.py`
  - `CODELY-ARCH-003`: confirmed direct `controller` (`direct_controller.py`) -> `data_access` (`order_repo.py`) dependency
  - `CODELY-ARCH-012`: unresolved internal import in `broken_imports.py`
  - `CODELY-ARCH-010`: 4-level inheritance hierarchy (`PremiumAccountEntity -> AccountEntity -> AuditedEntity -> BaseEntity`) in `domain_hierarchy.py`
  - `CODELY-ARCH-009`: 7 effective parameters in `dispatch_order` in `domain_hierarchy.py`
- `routes.py -> order_service.py -> order_repo.py` passes layer rules cleanly, and
  `standalone_helpers.py` produces zero false positives.

## Limitations and interpretation guidance

- Observations represent static structural evidence and configurable heuristics, not
  runtime bugs, security vulnerabilities, or proof of performance bottlenecks.
- Dynamic imports, reflection, monkey-patching, runtime `sys.path` changes, and unknown
  external packages limit import-graph completeness.
- Filename-based roles (`inferred`) are heuristic; confirm actual module responsibilities
  before enforcing architectural changes.
- All recommendations are advisory and require human review; no automated code rewrites,
  quality scores, or runtime performance guarantees are produced.

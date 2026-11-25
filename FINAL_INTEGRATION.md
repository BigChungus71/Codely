# Final Pipeline and Team Integration Guide

Phase 9 delivers the unified end-to-end orchestration entry point
(`backend/app/analyzers/pipeline.py`), integration-ready payloads for the FastAPI
backend, React/React Flow frontend, and Gemini explanation layer, multi-language
demonstration fixtures, and measured fixture benchmarks.

## Unified public interface

```python
from backend.app.analyzers.architecture_policy import load_policy
from backend.app.analyzers.pipeline import PipelineOptions, run_analysis_pipeline

policy = load_policy("contracts/examples/architecture-policy-v1.json")
result = run_analysis_pipeline(validated_repository_path, policy=policy)

full_payload = result.to_dict()
frontend_payload = result.frontend_payload(project_id="proj-123")
gemini_bundle = result.gemini_context()
```

CLI usage:

```powershell
# Full pipeline JSON (exit 0 when status == "complete", 2 when "partial" or "error")
python -m backend.app.analyzers.pipeline fixtures/fullstack_demo --policy contracts/examples/architecture-policy-v1.json

# Frontend/FastAPI payload or compact Gemini evidence bundle
python -m backend.app.analyzers.pipeline fixtures/fullstack_demo --frontend
python -m backend.app.analyzers.pipeline fixtures/fullstack_demo --gemini-context
```

Stage reuse guarantees:
- `scan_repository` runs at most once per pipeline invocation (unless supplied or skipped).
- `analyze_repository` parses source files once.
- `build_architecture_graph`, `evaluate_repository`, `analyze_security_impact`, and
  `evaluate_architecture` reuse the single scan/structure/graph outputs from the same
  immutable repository snapshot.
- Partial failures and unsupported languages propagate explicitly; empty or failed stages
  never turn into clean `complete` status.

## Team integration contracts (FastAPI, React Flow, Gemini)

All teammate branches (`feature/backend-core`, `feat/frontend-workspace`) were inspected
and left unmodified:

- **FastAPI Backend (`backend/codely/schemas.py`, `adapters.py`)**:
  - Continue pointing `CODELY_SCANNER_ADAPTER` at
    `backend.app.analyzers.backend_adapter:scan_repository` for isolated scanning, or invoke
    `run_analysis_pipeline(validated_path, policy=policy).frontend_payload(project_id=...)`
    in a background worker to retrieve all 6 stage outputs in one pass.
  - `frontend_payload()['scan']` preserves `Finding` fields, `ScanCoverage`
    (`detected_languages`, `analyzed_languages`, `unsupported_languages`, `rule_sets`,
    `scanned_files`, `excluded_files`, `excluded_directory_count`, `unscanned_supported_files`),
    and non-empty `errors` whenever `scan.status != "complete"`.
  - `frontend_payload()['architecture']` includes `graph_type: "dependencies"`, `status`,
    `nodes`, `edges` (with `confidence` and `evidence`), `statistics`, `diagnostics`, and
    `coverage`.
- **React / React Flow Frontend**:
  - Render `scan.findings` separately from `architecture_evaluation.observations`.
  - Style `potential_api_call` edges (`confidence == "inferred"`) distinctly from confirmed
    `imports`, `inherits`, `implements`, and `references_component` edges.
  - Highlight ASIM `direct_dependent_node_ids`, `transitive_dependent_node_ids`,
    `relevant_edge_ids`, and `inferred_relationships` without copying original finding
    severity onto dependent modules.
- **Gemini Explanation & Remediation Layer**:
  - Pass `result.gemini_context()` (or `observations.gemini_evidence_package()` for
    architecture-only explanations) as structured context.
  - Contains `safety_notice`, `repository_profile`, `security_findings` (normalized metadata,
    enclosing symbols, ASIM dependency paths, inferred links), `checklist_highlights`,
    `architecture_evidence`, and `analysis_limitations`.
  - Excludes source literals, secret values, raw stderr, quality scores, and runtime
    performance claims; treats repository identifiers as untrusted data.

Schemas & representative payloads:
- Unified schema: `contracts/unified-pipeline-v1.schema.json`
- Representative mixed-language example: `contracts/examples/unified-pipeline-v1.json`

## End-to-end demonstrations (`fixtures/`)

| Fixture | Languages & Frameworks | Key Demonstrated Capabilities |
| --- | --- | --- |
| `fixtures/impact_demo` | Python, Flask | SQLi detection (`codely.python.sql-injection`), cycle handling, ASIM dependents (`unrelated.py`/`auth.py` excluded) |
| `fixtures/spring_boot_demo` | Java, Spring Boot, Spring MVC, Maven | Java SQL concatenation (`codely.java.sql-concatenation`), Tree-sitter mapping (`OrderRepository.findByStatus`), ASIM `OrderService` -> `OrderController` (`UnrelatedHealthController` excluded), checklist `PASS`/`FAIL` |
| `fixtures/express_demo` | JavaScript, Express, npm | JS SQL concatenation, insecure cookie, open redirect (`codely.web.*`), CommonJS resolution, ASIM `userService.js` -> `users.js` (`formatters.js` excluded) |
| `fixtures/fullstack_demo` | Python + TSX, FastAPI + React | Dual-language Semgrep (`sql-injection` + `dangerously-set-inner-html`), TS `@/*` path alias, `references_component` + inferred `potential_api_call`, ASIM + Gemini bundle |
| `fixtures/architecture_rules_demo` | Python, FastAPI, Flask | Cycle (`001`), controller->data_access (`003`), unresolved import (`012`), 4-level inheritance (`010`), 7-param function (`009`), zero false positives on `routes.py`/`standalone_helpers.py` |

## Actual performance measurements

Measured via `python tools/benchmark_pipeline.py` on Windows 10/11 (`Windows-10-10.0.26300-SP0`),
Python `3.11.9`, Semgrep `1.187.0`, NetworkX `3.6.1`, Tree-sitter `0.27.0` (outside restricted sandbox):

| Repository | Files (Parsed) | Status | Findings | Nodes / Edges | Obs | Scan (ms) | Structure (ms) | Graph (ms) | Checklist (ms) | Impact (ms) | Rules (ms) | Total (ms) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `fixtures/impact_demo` | 7 (7) | `complete` | 1 | 7 / 6 | 1 | 3242.06 | 6.73 | 1.71 | 7.06 | 0.80 | 0.49 | 3258.86 |
| `fixtures/spring_boot_demo` | 5 (5) | `complete` | 1 | 5 / 2 | 0 | 3140.69 | 12.16 | 0.62 | 13.33 | 0.83 | 0.66 | 3168.33 |
| `fixtures/express_demo` | 4 (4) | `complete` | 3 | 4 / 2 | 0 | 3284.79 | 7.30 | 0.55 | 7.60 | 0.83 | 0.29 | 3301.38 |
| `fixtures/fullstack_demo` | 8 (8) | `complete` | 2 | 8 / 6 | 0 | 3430.34 | 11.96 | 0.71 | 12.32 | 0.76 | 0.40 | 3456.52 |
| `fixtures/architecture_rules_demo` | 8 (8) | `partial` | 0 | 8 / 5 | 5 | 3300.72 | 7.53 | 0.77 | 7.32 | 0.24 | 0.53 | 3317.13 |

*Note*: These are small synthetic fixture timings, not production-scale repository benchmarks.
Over 99% of single-repo runtime is Semgrep CLI startup (`~3.1–3.4s`); all Python/Tree-sitter/NetworkX
analysis stages combined complete in `16–27 ms`.

## Known limitations

- Native Semgrep requires execution outside restricted Windows sandboxes due to `semgrep-core` `socketpair` errors inside AppContainer sandboxes.
- Live HTTP integration against teammate branches (`feature/backend-core`, `feat/frontend-workspace`) was not merged or executed in this branch; payloads and contracts were verified via schemas and branch contract inspection.
- Static findings never establish runtime exploitability, and zero findings never prove an application is secure.

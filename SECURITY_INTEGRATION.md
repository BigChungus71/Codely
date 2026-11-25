# Shared repository security integration

Security branch starts at main 0805457b96a2f60e768bd9efbc22e091f3f1d89b.
main has only the CodeRAG archives and README. The teammate backend at
origin/feature/backend-core (ada47e4) and frontend at origin/feat/frontend-workspace
were inspected but not merged or modified. All security files are additive.
The original C:/Users/bharg/codely implementation remains an untouched backup.

## Scanner use

From repository root, install requirements-security.txt in a trusted environment
and call backend.app.analyzers.semgrep_adapter.scan_repository(path).to_dict().
Use contracts/security-scan.schema.json for the unchanged finding/envelope shape.
The exact Windows freeze is requirements-security-windows.lock.txt; the shared
backend's dependency files must not be replaced with that freeze.

The backend's codely.schemas.Finding has the same required fields (plus optional
evidence). Its ScanResult requires findings and errors; codely.api.validated_scan
rejects nonempty errors before caching. Use the compatibility hook rather than
passing the core dataclass directly:

```powershell
# When running from backend/ after the team combines the branches:
$env:CODELY_SCANNER_ADAPTER = "app.analyzers.backend_adapter:scan_repository"
# When running with repository root on sys.path instead:
$env:CODELY_SCANNER_ADAPTER = "backend.app.analyzers.backend_adapter:scan_repository"
```

The hook adds errors for every partial/error result so incomplete analysis cannot
be cached as a clean scan. It changes neither the core contract nor teammate API
code. No architecture/explanation hook is implemented. The main branch currently
has no backend API; backend wiring is documented against the inspected teammate
branch, not claimed as a live end-to-end deployment.

## Tests

Native Windows scanning requires a normal process outside the restricted sandbox.
No uploaded code, dependency installer, registry rule or cloud service runs.
The original local virtual environment can test this checkout without copying it:

```powershell
$env:CODELY_RUN_SEMGREP_INTEGRATION = "1"
C:/Users/bharg/codely/.venv/Scripts/python.exe -m pytest -q
C:/Users/bharg/codely/.venv/Scripts/python.exe tools/verify_semgrep.py
```

See SECURITY_README.md, backend/app/rules/README.md and SETUP_REPORT.md for
coverage and limitations. Reference source snapshots/provenance are inactive.
No teammates' backend/frontend modules, archive bytes, or root README were changed.

## Migration verification (2026-11-25)

75 tests passed in 13.55s: the original 72 checks, including all 17 real native
Semgrep tests, plus three backend-hook status tests. The original compatibility
probe also passed (vulnerable=1, safe=0, errors=0). This validates security
modules and the hook contract, not live endpoints from other branches.

## Phase 3 worker integration

The migration was pushed and verified as aecdcfe10c199ff8afa89bf5488d8c00394fae0f
on security-analysis. main and teammates' branches were not updated.

Keep the original full ScanResult available and call
`backend.app.checklists.evaluate_repository(path, scan_result).to_dict()` before
converting it to the backend's findings/errors-only model. No additional scan
is performed. See CHECKLIST_INTEGRATION.md and contracts/checklist-v1.schema.json.
The scanner hook remains backward compatible; no backend endpoint is added.

Full Phase 3 regression: 149 passing tests (130 unit/static, 19 native). The
original twelve security rules and 37-fixture/25-finding expectations still pass.
The new demo output is committed in contracts/examples/checklist-v1.json and
compared exactly against real native scanner/checklist output in tests.

## Phase 4 structure worker seam

Call `backend.app.analyzers.structure_analyzer.analyze_repository(path).to_dict()`
from repository root, or use `app.analyzers.structure_analyzer` from backend/.
This is a distinct repository-structure contract, not the `{nodes, edges}`
architecture-hook response. Do not plug it directly into that hook. Future graph
work can aggregate its explicit import edges; no API or graph adapter is added.
Enclosing-symbol helpers accept a relative file and line for future evidence
context lookup; no Gemini call or automatic source export occurs.

Phase 3 remote completion at 98b9d8d was verified first. Full Phase 4 regression:
210 passed, including all prior 19 native tests; 61 tests cover the new AST engine.
See STRUCTURE_INTEGRATION.md for capabilities, uncertainty and limits.

## Phase 5 graph worker seam

Reuse the existing RepositoryStructure with
`backend.app.analyzers.architecture_graph.build_architecture_graph(structure)`.
The graph keeps required nodes/edges fields and adds optional evidence, statistics,
status and coverage. No scanner, checklist or AST code/contract is modified.

The teammate backend hook expects path -> dict, not a structure object. Its
current Pydantic Graph discards richer metadata and does not check partial status;
the API owner must preserve/check those fields before exposing the full graph.
No teammate-owned adapter/API/schema/frontend was changed in this phase. See
ARCHITECTURE_INTEGRATION.md for integration and the React Flow presentation map.
Full regression: 281 passing tests, including the original 19 native tests.

## Phase 6 ASIM worker seam

Pass the original full ScanResult, RepositoryStructure and ArchitectureGraph to
`backend.app.analyzers.impact_analyzer.analyze_security_impact`. From backend/,
use app.analyzers instead. No scan, parse or graph build occurs inside ASIM.
Preserve the same immutable repository version across inputs. Cross-input
references are checked, but complete snapshot identity is caller-owned.

The separate security-impact-v1 schema exposes mapped/unmapped findings, shared
module analyses, existing node/edge IDs, shortest-path evidence and explicit
coverage/truncation. It does not change legacy finding/graph responses. Backend
owners should preserve this metadata in a separate endpoint/envelope if exposing
it; no API/frontend/Gemini module was changed. The evidence_for_finding helper
prepares selected nontext metadata for the existing GenAI team. See
IMPACT_INTEGRATION.md for frontend highlighting, privacy and interpretation.

Actual full regression: 342 passing tests, including 22 native-backed integration
tests. Actual native demo: one mapped finding, zero unmapped, one direct and
three transitive dependents. Original CodeRAG provenance remains unchanged.

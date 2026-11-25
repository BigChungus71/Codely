# Codely â€” Security and Code Intelligence

Rules decide, AI explains. This workspace contains the Python environment,
verified native Semgrep compatibility probe, and a deterministic
security scanner adapted for the supplied CodeRAG integration base. Scope is
Security and Code Intelligence only. See AGENTS.md for ownership, contracts,
the roadmap and safety requirements, and CODERAG_INTEGRATION.md for the supplied
base, active scanner interface and remaining integration work.

## Windows setup (PowerShell)

Use Python 3.11 and run these commands from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-security.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest --version
New-Item -ItemType Directory -Force .semgrep-local | Out-Null
$env:SEMGREP_LOG_FILE = "$PWD\.semgrep-local\semgrep.log"
$env:SEMGREP_SETTINGS_FILE = "$PWD\.semgrep-local\settings.yaml"
$env:SEMGREP_VERSION_CACHE_PATH = "$PWD\.semgrep-local\version"
$env:SEMGREP_SEND_METRICS = "off"
$env:SEMGREP_ENABLE_VERSION_CHECK = "0"
.\.venv\Scripts\semgrep.exe --version
```

Skip environment creation if `.venv` already exists. Explicit executable paths
avoid activation and PowerShell execution-policy changes. Installation requires
access to the configured Python package index. The direct requirements are isolated from the backend/RAG dependency lists.
requirements-security-windows.lock.txt preserves the exact tested Windows
environment; resolve a platform-appropriate environment on Linux.

## Layout

- `backend/app/analyzers/`: repository scanner and JSON command-line interface.
- `backend/app/rules/`: trusted local scanner rules and compatibility probe.
- `backend/tests/`: isolated scanner contract and failure-path tests.
- `fixtures/`: static safe/vulnerable source fixtures, never executed.
- `contracts/`: reserved for integration schemas; required fields are in AGENTS.md.
- `reference/coderag/`: preserved source base and provenance, not active packages.
- `tools/verify_semgrep.py`: native fixture and JSON verification.

Run tests with `.\.venv\Scripts\python.exe -m pytest -q`. The pytest configuration
limits collection to Codely's tests; supplied CodeRAG tests are reference only.
Run the expanded security pipeline from a normal PowerShell session with:

```powershell
.\.venv\Scripts\python.exe -m backend.app.analyzers fixtures/security_rules
```

The local pack has 12 rules: eval, exec, SQL injection, shell command injection,
hardcoded credentials, untrusted pickle, unsafe YAML, weak password hashing,
disabled TLS verification, insecure temporary filenames, Flask debug mode and
predictable security randomness. See [the rule catalog](backend/app/rules/README.md)
for exact APIs, input sources, metadata and limits. SQL, shell, pickle and
security-randomness checks use taint mode. No comprehensive vulnerability or
OWASP compliance coverage is claimed. No FastAPI server or cloud services run.

Phase 2 verification on Python 3.11.9 / Semgrep 1.187.0: 55 non-integration tests
and 17 real native integration tests pass. The real fixture scan covers 37 nested
Python files with exactly 25 expected findings; the 12-file safe scan has zero
findings and complete supported-file coverage. See SETUP_REPORT.md for evidence.

```powershell
# Default tests: mocked boundaries plus offline schema/catalog checks.
.\.venv\Scripts\python.exe -m pytest -q
# Offline rule syntax/schema validation (native core, no registry).
.\.venv\Scripts\python.exe tools\validate_security_rules.py
# Full suite including actual scanner processes, outside the restricted sandbox.
$env:CODELY_RUN_SEMGREP_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:\CODELY_RUN_SEMGREP_INTEGRATION
```

Without the opt-in variable, native tests are skipped explicitly; a default test
run alone does not verify scanner execution. CLI exit 0 means `complete` scanning
of the configured rule/file scope, whether findings exist or not. Exit 2 and
`partial`/`error` status mean incomplete coverage or failure. Callers must inspect
status before interpreting an empty findings list.

## Analysis boundaries

Security scanning is mandatory and precedes architecture enhancements. Never
execute uploaded source, install its dependencies, or load its scanner settings.
The scanner validates repository boundaries, uses relative paths, runs bounded
subprocesses with `shell=False`, and reports errors and coverage gaps.
An import graph is not a complete runtime call graph. Findings do not prove
exploitability, and zero findings do not establish that an application is secure.

## Environment verification

See SETUP_REPORT.md for the observed versions, verification results, and native
Windows / WSL status. WSL is a fallback only if native Semgrep proves unreliable;
do not reuse the Windows `.venv` inside WSL. No remote repository, commit, or push
is part of this initialization.

Native scanner execution is verified outside the Codex restricted sandbox.
Run `.\.venv\Scripts\python.exe tools\verify_semgrep.py` from a normal local
PowerShell session to check both fixtures and parse the resulting JSON. Inside
the restricted sandbox, `semgrep-core` fails at `socketpair`; this does not
require reinstalling the scanner. See the Phase 1.1 report for exact evidence.

## Phase 3 reference checklist

The versioned 15-check catalog complements the scanner without changing finding
fields or rescanning inside the evaluator. Use `backend.app.checklists.evaluate_repository`
with the existing ScanResult. See [CHECKLIST_INTEGRATION.md](CHECKLIST_INTEGRATION.md)
for statuses, limitations and worker integration, and
[representative JSON](contracts/examples/checklist-v1.json) for a real fixture result.

```powershell
python -m backend.app.checklists fixtures/checklist_demo
```

Phase 3 verification: 149 tests pass, including 19 actual native tests and all
original scanner regressions. The demo scans two Python files, returns two
synthetic security findings, and evaluates to 8 PASS / 2 FAIL / 1 NEEDS_REVIEW /
4 NOT_APPLICABLE. No code from that repository is executed. No Phase 4 work, API
endpoints or frontend implementation is included.

## Phase 4 repository structure

`backend.app.analyzers.structure_analyzer.analyze_repository(path)` returns a
versioned JSON-serializable RepositoryStructure without executing/importing target
source. It extracts symbols, imports, direct dependency evidence, call syntax and
framework/component indicators. Enclosing-function/class helpers prepare source
context navigation without invoking Gemini.

See [STRUCTURE_INTEGRATION.md](STRUCTURE_INTEGRATION.md),
[the schema](contracts/repository-structure-v1.schema.json) and
[the exact fixture example](contracts/examples/repository-structure-v1.json).
The example is intentionally partial because it includes an invalid Python file.

```powershell
python -m backend.app.analyzers.structure_cli fixtures/structure_demo
```

Phase 4 verification: 61 new AST tests and 210 total passing tests, including
19 native scanner/checklist tests. No dependencies or prior finding/checklist
contracts changed. Import evidence is not a complete runtime call graph.
No Phase 5 graph or impact mapping is implemented.

## Phase 5 architecture dependencies

Build an observed import graph from existing structure without parsing again:

```python
from backend.app.analyzers.architecture_graph import build_architecture_graph
architecture = build_architecture_graph(structure)
payload = architecture.to_dict()
```

The NetworkX DiGraph preserves importer -> imported direction, merged import
evidence, confidence-labeled roles, graph metrics, SCC/cycle witnesses and bounded
forward/reverse traversal helpers. See [ARCHITECTURE_INTEGRATION.md](ARCHITECTURE_INTEGRATION.md),
[the schema](contracts/architecture-graph-v1.schema.json) and
[the representative JSON](contracts/examples/architecture-graph-v1.json).

Phase 5: 281 total passing tests, including 71 new graph tests and all 19 native
scanner/checklist tests. No extra dependency is installed. This is static import
evidence, not a complete runtime call graph or quality/security verdict. No full
Phase 6 vulnerability impact mapper or frontend/API implementation is included.

## Phase 6 architectural security impact

Reuse existing scan/structure/graph objects without rerunning those stages:

```python
from backend.app.analyzers.impact_analyzer import analyze_security_impact
impact = analyze_security_impact(scan, structure, architecture)
payload = impact.to_dict()
package = impact.evidence_for_finding(finding_id)
```

ASIM links original findings to parsed source symbols and graph nodes, then uses
bounded reverse import traversal for potential dependent relevance. Severity stays
with the original finding; dependents are not assigned vulnerabilities. See
[IMPACT_INTEGRATION.md](IMPACT_INTEGRATION.md),
[the schema](contracts/security-impact-v1.schema.json) and
[actual demonstration JSON](contracts/examples/security-impact-v1.json).

Native demo: one HIGH SQL-injection finding mapped to database.py:11 /
Repository.lookup; one direct and three transitive dependent modules, with
unrelated/auth modules excluded and circular imports handled safely.
Final regression: 342 tests pass, including all 22 native-backed tests.
No new dependency, prior contract change, Gemini call or Phase 7 implementation.

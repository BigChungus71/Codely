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

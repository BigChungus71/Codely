# Phase 1 setup report

Observed on 2026-11-25 in Windows PowerShell.

## Repository and files

The initial directory contained only `.git`. Git reported no commits on
`feature/security-analysis` and no working tree changes. No branch was changed,
remote repository created, commit made, or push performed.

Created `AGENTS.md` with the supplied project overview, ownership, roadmap,
contracts, safety requirements and Phase 1 scope; `.gitignore`; `README.md`;
this report; `requirements.txt`; and a local ignored `.venv`.

Created `backend/__init__.py`, `backend/app/__init__.py`,
`backend/app/analyzers/__init__.py`, `backend/app/rules/__init__.py`, and
`backend/tests/__init__.py`. Created `fixtures/.gitkeep` and
`contracts/.gitkeep`. No analyzer implementations or additional contracts were
introduced. Temporary smoke fixtures were removed automatically.

## Observed versions and checks

| Tool | Version | Result |
| --- | --- | --- |
| Python | 3.11.9 | Interpreter and venv creation succeeded |
| Global pip | 26.3 | Version command succeeded |
| Virtual environment pip | 24.0 | Installation, freeze and dependency check succeeded |
| Git | 2.56.0.windows.4 | Version and status succeeded |
| Semgrep | 1.187.0 | Installed; version command succeeded with local state paths; scan failed |
| NetworkX | 3.6.1 | Import and directed graph ancestor traversal passed |
| pytest | 9.2.0 | Import and CLI version passed; no application test suite exists |

`pip check` returned exit code 0: `No broken requirements found.`
`requirements.txt` is the actual `pip freeze` output, including transitive
dependencies. No uploaded repository dependencies were installed.

## Compatibility and blockers

Initial package installation failed because the restricted environment could
not resolve the package index. The network-enabled permission retry completed
successfully, using a native Windows Semgrep wheel.

Semgrep initially failed to start because writing `C:\Users\bharg\.semgrep`
was denied. Redirecting `SEMGREP_LOG_FILE`, `SEMGREP_SETTINGS_FILE`, and
`SEMGREP_VERSION_CACHE_PATH` into the workspace allowed `--version` to return
1.187.0 (exit code 0). README includes those settings.

A bounded `shell=False` scan of a temporary Python text file containing
`eval(user_input)` with a trusted temporary YAML pattern rule failed:

```text
CLI exit code: 2
stdout: <ERROR: missing output>
RPC subprocess failed: semgrep-core exited with code 1.
semgrep-core rule validation failed (SemgrepError)
```

The source text was never executed. Metrics and version checks were disabled.
The root cause of the native core failure remains unresolved; scanner operation
is not verified. Windows cp1252 also failed while decoding/displaying scanner
diagnostics; the final diagnostic capture used bytes and explicit UTF-8 decoding.
Future scanner handling must preserve output safely across encodings.

`wsl.exe` exists at `C:\WINDOWS\system32\wsl.exe`, but both `wsl --status` and
`wsl --list --quiet` returned exit code 1 with `The system cannot find the path
specified.` No usable distribution or WSL2 runtime was verified. No system WSL
installation or configuration changes were made. Native scanner diagnosis or a
working WSL2 environment is required before the core scanning pipeline can be
validated. Work stopped at Phase 1 as requested.

## Phase 1.1 — scanner compatibility resolution (2026-11-25)

The earlier scanner blocker is resolved for native Windows execution outside
the Codex restricted sandbox. No packages or system settings were changed.

The debug reproduction returned CLI exit code 2, core exit code 1, and:

```text
exn Unix_error: The data area passed to a system call is too small.
 socketpair
Raised at UCommon.main_boilerplate.(fun) in OSS/libs/commons/UCommon.ml:126
Called from UCommon.pp_do_in_zero_box in OSS/libs/commons/UCommon.ml:59
Called from Stdlib__Fun.protect in fun.ml:34
Called from Common.protect in OSS/libs/commons/Common.ml:53
Called from Common.finalize in OSS/libs/commons/Common.ml:146
Called from UCommon.exn_to_real_unixexit in OSS/libs/commons/UCommon.ml:43
RPC subprocess failed: semgrep-core exited with code 1.
```

Full raw debug stderr and stdout are saved locally in the ignored
`.semgrep-local/native-scan.stderr` and `.semgrep-local/native-scan.stdout`.
The core binary itself successfully returned version 1.187.0. Repeating the
same local fixture scan outside the restricted sandbox succeeded. This isolates
the observed failure to the restricted execution context's socketpair behavior;
the exact Windows sandbox internals were not inspected. There is no evidence
that a Python downgrade, missing DLL installation, or scanner reinstall is
needed. Existing Python 3.11.9 and Semgrep 1.187.0 work together here.

Added a trusted local rule at `backend/app/rules/compatibility-smoke.yaml` and
static safe/vulnerable text fixtures in `fixtures/semgrep_compatibility/`.
`tools/verify_semgrep.py` uses `shell=False`, a 60-second subprocess timeout,
workspace-local Semgrep state, byte capture, and JSON parsing. It checks both
files were scanned, no errors occurred, and the sole expected finding is on
line 3 of `vulnerable.py`. Neither fixture is imported or executed.

Working verification command, from the repository root in Windows PowerShell
outside the Codex restricted sandbox (or with an approved sandbox escalation):

```powershell
.\.venv\Scripts\python.exe tools\verify_semgrep.py
```

Observed exit code 0 and:

```text
PASS: JSON parsed; both fixtures scanned; vulnerable=1, safe=0; errors=0
```

The exact scanner argument vector used by the verifier is:

```powershell
.\.venv\Scripts\semgrep.exe scan --config backend/app/rules/compatibility-smoke.yaml --json --metrics=off --disable-version-check --no-git-ignore fixtures/semgrep_compatibility
```

The verifier sets the local state variables documented in README and
`PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8`. JSON and stderr are preserved in
`.semgrep-local/verification.json` and `.semgrep-local/verification.stderr`.
No registry rules or online services are used. The fixture rule is only a
compatibility probe; it is not a production security coverage claim.

WSL checks also failed outside the sandbox: `wsl --status` and
`wsl --list --verbose` both exited 1 with UTF-16LE stderr `The system cannot find
the path specified.` The Windows launcher exists (file version 10.0.26100.8737),
but `C:\Program Files\WSL\wsl.exe` is absent. The per-user Lxss registry key
exists but returned no default distribution/version. No matching WSL/Lxss
service was reported by the unrestricted service query. These observations
show an unusable WSL installation; the launcher does not disclose which path
is missing, so the exact underlying missing component is not established.

Docker is unavailable on PATH (`docker version` raises FileNotFoundError,
WinError 2), its standard Docker Desktop CLI path is absent, and no matching
Docker service was reported. No operational Docker engine was verified.

Recommended execution approach: retain the working native virtual environment
and run the scanner from a normal local process outside this restricted sandbox.
There is no present need for a Linux fallback. If a deployment later requires
Linux isolation, provision and verify WSL2 or Docker separately with explicit
approval. No Windows features, security settings, services, installations,
restarts, commits, or pushes were performed.

## Supplied CodeRAG base adaptation

The user subsequently supplied `coderag-backend-main.zip` and
`coderag-extension-main.zip` and explicitly confirmed Security and Code
Intelligence only. Selected original source/manifests were retained under
`reference/coderag/` with per-file and archive SHA-256 provenance. Stored
indexes/pickle data, logs, cloud deployment configuration and workflows were
not imported. Neither archived code nor archived dependency installers ran.
No existing virtual environment dependencies changed.

Implemented the active repository scanner in
`backend/app/analyzers/semgrep_adapter.py`, exposing the requested
`scan_repository(project_path: str) -> ScanResult` interface and JSON CLI.
It replaces the supplied base's lint/confidence approach at the integration seam
with deterministic local Semgrep findings, severity/CWE normalization, stable
IDs, bounded snapshots, timeout handling and explicit coverage/error status.
Rule IDs use `--no-rewrite-rule-ids` to avoid leaking local paths into the
shared contract. The initial rule detects dynamic Python eval only.

Native integration verification outside the restricted sandbox scanned both
safe/vulnerable fixtures and parsed the JSON. Observed status `complete`,
scanner exit 0, two scanned files, one MEDIUM finding at `vulnerable.py:3`,
rule `codely.python.dynamic-eval`, CWE-95, and no finding in `safe.py`.

`python -m pytest -q` in the existing virtual environment passed 11 tests.
Tests cover normalization, stable IDs, errors with findings, timeout, invalid
JSON, external finding paths, file limits, safe scans, missing executables,
untrusted repository config exclusion and linked-file skipping. Pytest is
restricted to `backend/tests`, avoiding supplied cloud-dependent tests.

`CODERAG_INTEGRATION.md` documents the interface, changed behavior, limits and
remaining backend-owner integration. No FastAPI endpoint, frontend/extension,
Gemini service, embeddings or deployment was implemented or started. Checklist,
AST/graph analysis and impact mapping remain future work; no runtime call graph
or broad vulnerability coverage is claimed.

## Phase 2 — expanded security rule engine (2026-11-25)

Completed the user-authorized expanded deterministic Python rule engine. The
existing virtual environment and all 21 CodeRAG reference source hashes were
preserved. No dependency installations/changes, system changes, remote rules,
API calls by the scanner, endpoints, frontend work, commits or pushes occurred.
The fixture files were read, syntax-parsed and scanned, never imported or run.

### Rule implementation

Expanded `backend/app/rules/python-security.yaml` to 12 stable IDs:
`codely.python.dynamic-eval`, `dynamic-exec`, `sql-injection`,
`command-injection`, `hardcoded-credential`, `unsafe-pickle`, `unsafe-yaml`,
`weak-password-hash`, `tls-verification-disabled`, `insecure-tempfile`,
`flask-debug`, and `insecure-security-random` (each has the same full prefix).
Every rule has title, description, severity, CWE, relevant versioned OWASP review
tags or an empty tag list, remediation, and a reference URL. Existing eval ID
and severity are preserved. SQL, shell, pickle and security-randomness rules
use taint analysis; other rules target specific APIs, settings or naming context.
The rule catalog documents exact coverage and intentionally pins OWASP to the
2021 edition without claiming latest-edition or comprehensive compliance.

### Scanner and contract

Extracted strict finding normalization into `finding_normalizer.py`. The public
finding fields and `scan_repository(project_path: str) -> ScanResult` interface
remain unchanged. Added defensive JSON validation, Windows path normalization,
source-boundary/inventory checks, exact-duplicate removal and rejection of
conflicting duplicates. Same-line findings with different columns stay distinct.

`complete` means selected rules finished over the supported snapshot with no
reported coverage gaps. Nonzero process exits, malformed JSON, missing scanner,
timeouts and empty/unsupported-only repositories cannot become a successful empty
scan. Parse/coverage errors yield `partial` or `error`; raw scanner messages and
credential/source text are omitted from API diagnostics. Diagnostics retain
scanner exit codes/types, supported-file counts and skipped relative paths.

Syntax preflight uses Python 3.11 AST parsing without execution. This was needed
because the native Semgrep parser silently recovered from the malformed fixture
`def broken(:`. The scanner now marks that file as an explicit syntax coverage
gap while retaining findings from valid files. Newer Python syntax unsupported
by the host parser similarly causes incomplete coverage.

The snapshot has a trusted empty ignore file and an explicit non-VCS project
root. The engine ignores uploaded scanner/ignore settings and inline `nosemgrep`
suppressions. This fixes Semgrep's default omission of `tests/` paths. Explicit
targets with a bounded command-line budget handle uppercase `.PY` files; files
omitted due to that budget remain visible as coverage gaps. Hidden, nested and
space-containing paths are exercised by real tests. Snapshot resource limits
remain 1 MiB/file, 5,000 supported files and 50 MiB total, with a 60-second
scanner subprocess timeout and `shell=False`.

### Actual verification results

Environment: native Windows, Python 3.11.9, Semgrep 1.187.0, pytest 9.2.0,
outside the Codex restricted sandbox via approved execution. The sandbox's
socketpair limitation remains; no WSL/Docker installation was needed.

```powershell
$env:CODELY_RUN_SEMGREP_INTEGRATION = "1"
.\.venv\Scripts\python.exe -m pytest -q --junitxml=.semgrep-local/phase2-tests.xml
```

Observed **72 passed in 13.67s**, exit code 0, no skips. This includes:

- **55 unit/static checks**: mocked scanner boundaries, normalization/severity,
  Windows paths, duplicates, timeout, malformed JSON/fields, nonzero exits,
  partial errors, empty/invalid/unsupported inputs, snapshots, local schema and
  rule metadata. These checks alone do not prove scanner detection works.
- **17 native integration tests**, with no subprocess mocking: offline core
  compilation, all 12 rule detections and safe alternatives, exact nested
  finding/line/contract comparisons, a safe-only repository, syntax-error
  partial status and two distinct eval findings on the same source line.

The real nested-repository scan covered **37 Python fixtures** and returned
exactly **25 expected findings**, including hidden/test paths, uppercase suffixes,
spaces, import aliases, f-string SQL and joined random token generation. The
separate safe-only scan covered **12 files**, returned zero findings and had
`complete` status. JSON was generated and parsed in the real adapter for all
these scans. This verifies only the supported cases in the local rule catalog.

Offline rule validation uses `tools/validate_security_rules.py`: installed
Semgrep JSON schema plus native `semgrep-core -check_rules` with a local minimal
metacheck pack. The first attempt with an empty metacheck pack was rejected and
was corrected before the successful final suite. Semgrep 1.187.0's ordinary
`--validate` implementation fetches registry metachecks, so that network-based
validation path was not used. No community registry lint coverage is claimed.

The original `.\.venv\Scripts\python.exe tools\verify_semgrep.py` also passed
again: both fixtures scanned, vulnerable=1, safe=0, errors=0. All 21 entries in
`reference/coderag/manifest.json` matched their saved SHA-256 hashes.

### Files and integration

Modified the adapter and local production YAML; added the normalizer, rule
catalog, `fixtures/security_rules/` (37 static Python fixtures and an exact
expectation manifest), rule metadata/schema tests, mocked failure tests, opt-in
native tests and offline validation tool. Updated the existing config-exclusion
test for the trusted ignore file, pytest marker configuration, README,
CODERAG_INTEGRATION.md, AGENTS.md and this report. Original source/provenance and
requirements remain unchanged. The original compatibility probe is retained.

Use the existing backend call seam, or run from a normal PowerShell session:

```powershell
.\.venv\Scripts\python.exe -m backend.app.analyzers PATH_TO_VALIDATED_REPOSITORY
.\.venv\Scripts\python.exe tools\validate_security_rules.py
```

CLI exit 0 means complete scanning of the configured scope even when findings
exist; exit 2 means partial/error. The integration layer must propagate status
and diagnostics and attach project_id/scan_id. Rule remediation/OWASP/reference
metadata stays in the local catalog so the shared finding schema is unchanged.

Known limits: supported local sources/APIs only, OSS taint scope, no general
cross-file flow, credential/password/randomness naming heuristics, possible
shadowed API false positives, Python 3.11 grammar/UTF-8/source limits, generated
directory exclusions and no protection against concurrent hostile filesystem
replacement during snapshot creation. The caller must own and stabilize the
repository. Supported findings indicate reviewable risks, not exploitability;
zero findings does not establish repository security. Checklist, architecture,
impact mapping, API/backend wiring and frontend work remain out of scope.

# CodeRAG adaptation for Codely

Scope confirmed by the user: Security and Code Intelligence only. The supplied
backend and VS Code extension provide the integration base; their source is
preserved with provenance in `reference/coderag/`. The active Python security
implementation stays in the established `backend/app/` package. The FastAPI
server, embedding pipeline, extension, Gemini, database and deployment machinery
are not enabled or modified in this scope.

## CodeRAG adaptation

| Supplied behavior | Codely adaptation |
| --- | --- |
| `validator.py` lints a code string and returns text | Repository scanner returns structured status, summary, findings and diagnostics |
| `architect_service.py` asks Gemini for blast radius | Deferred to deterministic AST/import extraction and graph traversal in later authorized work |
| Architecture endpoints hardcode confidence 0.9 | No confidence or exploitability claims in scanner results |
| Backend `indexer.py` walks and embeds repository contents | Scanner uses a bounded local Python snapshot without embedding or executing source |
| Retriever loads pickle metadata | Scanner never reads stored indexes or deserializes uploaded pickle files |
| Extension approximates source lines from chunk indexes | Findings preserve exact Semgrep source lines and repository-relative paths |

The existing RAG confidence checks are not security verdicts. A completed scan
means this configured Python rule set ran, not that the application is secure.
The expanded v2 production rule set has 12 locally controlled rules. See
`backend/app/rules/README.md` for exact supported APIs, taint sources, severity,
CWE/OWASP metadata, remediation, references and known limits.

## Backend integration seam

The backend owner can call the pure Python interface from the repository root:

```python
from backend.app.analyzers.semgrep_adapter import scan_repository

result = scan_repository(validated_repository_path)
payload = result.to_dict()
# Attach project_id and scan_id in the backend integration layer.
```

This is a new structured repository-scan seam, not a drop-in response for the
existing CodeRAG `/lint` code-string request. The backend owner must validate
repository ownership and authorization before invoking it. Run blocking scanner
work in a worker appropriate to the eventual backend; no endpoint is added here.

The finding fields match AGENTS.md. `status`, `summary`, `findings` and
`diagnostics` are the scan envelope. Proposed status values are `complete`,
`partial`, and `error`; confirm these and diagnostic codes with the backend team
before external integration. `complete` is coverage of selected rules and
supported files only. Nonzero scanner exits, parse errors and coverage limits
are not silently treated as clean scans. Standard generated/vendor directories
and the supplied reference snapshot are explicitly excluded. Only UTF-8 Python
files with `.py` or `.PY` extensions are supported (1 MiB/file, 5,000 files,
50 MiB total); skipped
files and unreadable directories produce incomplete-coverage diagnostics.

Semgrep configuration always comes from the locally controlled
`backend/app/rules/python-security.yaml`. The adapter does not copy uploaded
scanner configurations. Symlinks/reparse points are skipped, paths are checked
against the repository, and the scanner sees only the temporary source snapshot.
The caller must keep repository contents stable during snapshot creation;
concurrent adversarial filesystem replacement is not covered by this local
initial implementation. A future ingestion/worker boundary must own the extracted
repository and deny mutation by other processes for the duration of scanning.
Python syntax is checked with Python 3.11's AST parser without executing it;
syntax errors, recursion limits and newer unsupported syntax are explicit
coverage gaps. Only supported, syntactically valid UTF-8 source is snapshotted.
The scanner's project root is forced to that snapshot, so ancestor ignore files
cannot influence targeting. A trusted empty `.semgrepignore` replaces defaults;
uploaded `.gitignore`, `.semgrepignore`, scanner YAML, and inline `nosemgrep`
cannot suppress analysis. Hidden paths, `tests/` paths, spaces and uppercase
Python extensions are verified. Many uppercase-extension explicit targets may
reach the bounded Windows argument budget; this yields partial coverage rather
than a clean result. Snapshot generation itself is not a hostile-code sandbox.

Findings are deduplicated by stable identity including rule, normalized file and
source coordinates. Separate findings on one line retain distinct IDs. Conflicting
duplicates or malformed fields make output invalid. Paths use forward slashes,
including normalized Windows input; network, drive-relative and escaping scanner
paths are rejected. Missing scanner coverage is recorded per repository file.

## Local use

Use normal Windows PowerShell outside Codex's restricted sandbox:

```powershell
.\.venv\Scripts\python.exe -m backend.app.analyzers fixtures/semgrep_compatibility
.\.venv\Scripts\python.exe tools/verify_semgrep.py
.\.venv\Scripts\python.exe tools/validate_security_rules.py
.\.venv\Scripts\python.exe -m pytest -q
```

CLI exit 0 means the scan completed (findings may be present). Exit 2 means
partial coverage or failure. Metrics and version checks are disabled. Raw stderr
and source excerpts are not included in API results, to avoid exposing source or
secrets; diagnostics retain exit status, scanner error types and coverage counts.
Compatibility-probe raw artifacts remain locally in ignored `.semgrep-local/`.
No additional dependencies are required beyond the existing requirements file.

Opt into real scans in the full test suite with
`$env:CODELY_RUN_SEMGREP_INTEGRATION = "1"` before running pytest outside the
restricted sandbox. Default tests exercise mocked subprocess failures, timeout,
malformed JSON, partial errors, Windows paths, duplicates, coverage, metadata and
offline schema validation. Native tests exercise all 12 rule detections and safe
counterparts, nested/hidden/test/uppercase paths, source positions, the unchanged
finding contract, syntax-error partial status, same-line findings and local core
rule compilation. On 2026-11-25: 55 non-integration tests and 17 native tests pass.

No source excerpt, raw error message or credential is returned in diagnostics.
Scanner exit codes, error types, coverage counts and skipped relative paths
remain available. Failure with no findings remains `error` (or `partial` when
coverage/parse errors occur with a successful process); it is never `complete`.
The backend must propagate this status and the diagnostics rather than converting
failures into a successful empty finding list. `project_id`/`scan_id` still belong
to the backend integration layer; remediation metadata remains in the local rule
catalog so the finding schema is unchanged.

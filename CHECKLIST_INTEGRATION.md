# Reference checklist v1.0.0

Phase 3 adds fifteen deterministic Python/security engineering indicators.
It does not add an API route, frontend, LLM call, runtime probe, dependency
installation, image build, dependency graph, or architecture analyzer.

## Consume an existing scan

```python
from backend.app.analyzers.semgrep_adapter import scan_repository
from backend.app.checklists import evaluate_repository

scan = scan_repository(validated_repository_path)       # exactly one scan
checklist = evaluate_repository(validated_repository_path, scan).to_dict()
```

The evaluator never invokes Semgrep. It accepts the original ScanResult or its
dictionary envelope. If the backend has already scanned, pass that result here
instead of scanning again. Do this before converting it to the teammate backend's
findings/errors-only Pydantic model, which discards coverage metadata. When the
backend runs from `backend/`, use `from app.checklists import evaluate_repository`
and `from app.analyzers.semgrep_adapter import scan_repository` instead.

The caller must provide a trusted scan from the **same stable repository
version** and keep its files immutable through both operations. This engine does
not infer identity from arbitrary JSON or validate a cache's project ownership.
The backend's existing repository-version/caching boundary remains responsible
for that. Scan input is schema-validated, source locations are checked against
the inventory, and unknown/missing scanner coverage cannot yield a scanner-based
PASS. The expected pack is `python-security-v2`, with a successful process exit.

`evaluate_repository(path)` without a scan is supported: scanner-dependent
checks become NEEDS_REVIEW; independent configuration indicators can still be
evaluated. The result coverage is partial. No hidden fallback scan occurs.

## Versioned catalog and output

The locally controlled catalog is `backend/app/checklists/catalog-v1.json`.
Internal IDs `CODELY-CHK-001` through `CODELY-CHK-015` are **Codely identifiers**,
not standard requirement numbers. Version 1.0.0 includes:

| Check | Evidence and assessment scope |
| --- | --- |
| Hardcoded credentials | Reuses supported Semgrep credential findings |
| Environment configuration | Static os.getenv/os.environ access indicator |
| Sensitive files and gitignore | Presence-only sensitive filenames; bounded root ignore glob policy |
| Production debug | Semgrep Flask finding; explicit FastAPI constructor/Django DEBUG flags |
| TLS verification | Reuses supported disabled-verification findings |
| Unsafe SQL construction | Reuses modeled source-to-query findings |
| Unsafe command execution | Reuses modeled shell flows and eval/exec findings |
| Password hashing | Reuses supported fast password-hash findings |
| Unsafe deserialization | Reuses modeled pickle flows and unsafe YAML loader findings |
| Permissive CORS | Recognized middleware/Flask-CORS calls and literal origins/credentials |
| Authentication indicators | Imports/decorators; coverage always requires review for web frameworks |
| Dependency manifest | requirements, pyproject, Pipfile, setup.py/setup.cfg presence |
| Dependency constraints | Requirements/PEP 621/build-system version specifiers only |
| Test suite presence | Python test filename indicators; tests are not run |
| Docker runtime user | Explicit final-stage USER directive; no image execution |

Each check returns its ID, description, status, reason, repository-relative
evidence, related finding IDs, reference URLs/categories, CWE where appropriate,
remediation, and limitations. Known source nodes have exact start/end lines;
file-presence evidence has no invented line number. No source snippets or secret
values are included. Existing scanner finding fields are unchanged.

Statuses mean:

- **PASS**: the narrowly described static indicator or complete local rule scope
  met the check. It does not prove overall security or compliance.
- **FAIL**: supported evidence contradicts that check (for example, a scanner
  finding, explicit debug=true, or an explicit root USER declaration).
- **NEEDS_REVIEW**: missing/indirect configuration, unknown policy, partial
  scanner/inventory coverage, or a claim that static analysis cannot establish.
- **NOT_APPLICABLE**: no supported technology/configuration indicator was found
  within complete static inventory; applicable scan checks also require complete
  scanner coverage before this result is returned.

Positive FAIL evidence is retained when scanner coverage is partial. A failed or
missing scan cannot turn a zero-finding result into a scanner-based PASS. Partial
static inventory downgrades PASS/NOT_APPLICABLE to NEEDS_REVIEW. Independent
manifest/configuration indicators can pass without a successful scanner; the
overall coverage remains partial. The summary is counts, not a compliance score.

The structured contract is `contracts/checklist-v1.schema.json`. The actual demo
output is `contracts/examples/checklist-v1.json`. It is generated by native
Semgrep plus the checklist over `fixtures/checklist_demo/`, not invented product
data: **8 PASS, 2 FAIL, 1 NEEDS_REVIEW, 4 NOT_APPLICABLE**. Two synthetic Semgrep
findings are reused with their exact IDs. The example contains no secret values.
Native tests compare the entire example to a fresh deterministic evaluation.

## Commands

From repository root, with a trusted environment containing requirements-security.txt:

```powershell
# Scan once and evaluate; prints checklist JSON.
python -m backend.app.checklists fixtures/checklist_demo
# Reuse trusted JSON from the same repository version; performs no new scan.
python -m backend.app.checklists REPOSITORY --scan-result CURRENT_SCAN.json
# Unit/static tests (native tests explicitly skipped).
python -m pytest -q
# Full native regression outside the Codex restricted sandbox.
$env:CODELY_RUN_SEMGREP_INTEGRATION = "1"
python -m pytest -q
```

CLI exit 0 means complete coverage of the configured scope, **even if checks
FAIL**. Exit 2 means partial/error coverage. Consumers must inspect coverage and
individual statuses; an HTTP/frontend adapter must preserve them. No endpoint is
implemented here. Catalog references are documentation links only; evaluating
them never downloads rules, calls reference sites or performs external API work.

## Boundaries and limitations

- The references include relevant OWASP cheat sheets, version-pinned 2021 review
  categories, CWE, Twelve-Factor Config, and official framework/packaging/Git/
  Docker docs. These are review anchors, not comprehensive OWASP/ASVS compliance.
  No standards ID is invented for engineering indicators with no direct mapping.
- Technology profiling is based on static imports and manifest/file presence.
  Imports are not proof that a package is installed or used at runtime. Dynamic
  imports, runtime aliasing/shadowing and custom framework wrappers are not
  generally resolved. AST use is limited to check/profile indicators, not Phase 4
  structural extraction or a dependency graph.
- Supported Semgrep inputs/APIs and OSS taint limits still apply. A PASS based on
  no supported finding is explicitly limited to that modeled rule scope.
- Environment access does not prove all secrets/config are externalized. Sensitive
  filenames can include public certificates; their contents are not read.
  Gitignore matching is a conservative root-only glob subset with basic ordered
  negation. Escaped/complex or nested ignore policies require review. Git tracking,
  commit history, global ignore settings and past secret exposure are not checked.
- Public wildcard CORS without credentials needs policy review; wildcard plus
  credentials fails this configuration check. Explicit literal allowlists are
  indicators only. Indirect CORS configuration and runtime behavior are unproven.
- Auth imports/decorators never establish coverage and cannot yield PASS here.
  No login attempt, route invocation or access-control test runs.
- Requirement pins/bounded ranges do not prove freshness, compatibility, installed
  versions, vulnerability absence or reproducible resolution. Direct URLs,
  requirements includes/options, dynamic/Poetry dependencies, setup.py and Pipfile
  constraint semantics require review; no package is fetched or installed.
- Docker USER is a declaration, not verified effective UID. Base-image defaults,
  inherited stage users, named user mappings, dynamic expressions and continuation
  syntax are not resolved; unknown final-stage state requires review.
- Inventory uses UTF-8, host Python grammar, 1 MiB/file, 5,000 inventoried files,
  50 MiB decoded-input budget and the scanner's documented directory exclusions.
  Linked/reparse paths are skipped. The caller must prevent concurrent adversarial
  file replacement; source inspection is not an operating-system sandbox.

No changes to the shared finding contract or teammate API modules were made.
Backend/frontend branches still need to be combined by the team; this module is
ready for their pure-Python worker integration seam. Phase 4 has not begun.

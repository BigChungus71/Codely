# Repository structure analyzer v1.0.0

Phase 3 completion was verified before this work: local and remote
`security-analysis` pointed to `98b9d8d`, with a clean tree and the saved
149-test passing report. Phase 4 is additive; the scanner, checklist and finding
contracts are unchanged. No graph, impact mapper, API, frontend or LLM is added.

## Public interface

```python
from backend.app.analyzers.structure_analyzer import (
    StructureOptions, analyze_repository, enclosing_function, enclosing_class,
    enclosing_symbols,
)

structure = analyze_repository(validated_repository_path)
payload = structure.to_dict()
function = enclosing_function(structure, "src/demo/services.py", 18)
cls = enclosing_class(structure, "src/demo/services.py", 18)
context = enclosing_symbols(structure, "src/demo/services.py", 18)
```

When running from `backend/`, import `app.analyzers.structure_analyzer` instead.
The optional keyword-only `options` accepts a StructureOptions object. Configure
positive `max_files`, `max_file_bytes`, `max_repository_bytes`, `max_entries`,
`max_ast_nodes` (per file), and `max_repository_ast_nodes` limits. Invalid limits
or escaping source roots raise ValueError rather than silently weakening limits.
`source_roots=("python",)` adds trusted repository-relative import candidates;
common `src` roots are discovered automatically. `external_modules=("company_sdk",)`
adds caller-declared external namespaces. Extra excluded directory names extend
mandatory exclusions; they cannot re-enable Git metadata or dependencies.

Defaults: 5,000 Python files, 1 MiB/file, 50 MiB total input bytes, 50,000 visited
file entries, 200,000 AST nodes/file and 1,000,000 retained AST nodes/repository.
Limits produce explicit partial coverage. Invalid/empty/unsupported-only roots
return error. Unreadable, linked/reparse, encoding-invalid, syntax-invalid and
over-limit files are recorded without source excerpts or raw exception messages.
Excluded directories are recorded separately and do not themselves mean failure.
The caller must own a stable repository and prevent concurrent file replacement.

The helper functions return the innermost enclosing declaration or None. The
combined helper returns the module plus all enclosing functions/classes ordered
innermost-first. It accepts forward-slash or Windows backslash relative paths;
absolute, drive-relative, UNC and escaping paths are rejected. Line numbers are
one-based. Decorator extents count as part of a declaration for these helpers;
`start_line` itself still points to `def`/`class`. No source text is read or sent
to Gemini by the helpers. They consume the in-memory RepositoryStructure object.

## Contract and identity

`contracts/repository-structure-v1.schema.json` is a separate versioned contract.
`contracts/examples/repository-structure-v1.json` is generated from
`fixtures/structure_demo/` and validated against that schema. It deliberately
reports partial coverage: thirteen Python module records, twelve parsed files,
one invalid fixture, four classes, eight functions, sixteen imports and seven
file-backed internal import relationships. There are two unresolved imports and
one dynamic import reference. Tests compare the full example to fresh output.

The output includes files, modules, classes, functions/methods, assignment symbols,
imports, call syntax, internal and external/stdlib dependency evidence, framework
indicators, classifications, unresolved references, diagnostics and coverage.
Definitions and import records retain source locations. Module bounds may be
null for empty/unreadable files. Columns are zero-based UTF-8 byte offsets as
reported by Python AST, not Monaco's UTF-16 columns; navigate by line or convert
against the decoded source. PEP 263 encoding cookies and UTF-8 BOMs are supported.
This broadens structure discovery only; the scanner/checklist encoding contracts
have not changed.

Module IDs hash relative paths. Named symbol IDs hash kind, file, qualified name
and duplicate-declaration ordinal. They survive unrelated line/body changes;
renaming/moving a declaration or inserting another same-name declaration can
change its ID. Import/call/framework event IDs include source coordinates and
can change when those statements move. IDs contain no source values or machine
paths. Repeated analysis of the same bytes/options on the same Python version
is deterministic; filesystem traversal and serialized record ordering are sorted.
Fixture line endings are fixed to LF to make the committed example repeatable.

## Import resolution

Absolute imports, relative levels, package `__init__.py` files, import aliases,
nested packages, namespace directories and common src layouts are supported as
static candidates. Resolution does not invoke Python import machinery, inspect
installed packages or modify sys.path. Direct class/function/assignment/import
declarations support `from module import member` evidence; no wildcard member
expansion or general re-export evaluation occurs.

- **internal**: one file-backed local target, or an explicit namespace-directory
  candidate with no fabricated source file. Only unique file-backed targets
  produce internal dependency records.
- **ambiguous**: multiple local candidates (including module/package or
  attribute/submodule collisions). No relationship is asserted.
- **stdlib**: an unshadowed name from the host's `sys.stdlib_module_names`.
  This identifies namespace membership, not platform availability or member validity.
- **external**: a recognized supported library namespace or caller-declared
  external module, after checking for local shadows. This does not prove that
  a distribution is installed or that an imported member exists.
- **unresolved**: missing/unknown modules, missing static attributes, invalid
  relative levels or nonpackage parent conflicts. Unknown packages are not
  automatically treated as verified external dependencies.

Every file-backed dependency has source/target module IDs, `import_id`, relative
source file and statement lines. It represents direct **import syntax**, including
conditional/function-local imports, not guaranteed runtime execution. Implicit
parent-package effects, import hooks, packaging configuration, runtime sys.path,
conditional activation and dynamic loading are not evaluated. Most-specific src
layout is used for relative anchors; nonstandard layouts should supply roots and
review unresolved/ambiguous records. Namespace-only imports retain actual directory
paths without inventing module files. Imports to unparsed source files explicitly
mark `target_parsed=false`.

`status=complete` means discovery/extraction finished within the supported file
scope, not that all references resolved. Coverage separately counts unresolved
and ambiguous imports and dynamic call sites. External dependency counts are
import-record counts, not unique installed-package counts. Same-pair import
relationships are kept per statement to preserve all evidence. Cyclic import
evidence is retained, but cycle detection is not implemented in Phase 4.

## Structural and framework evidence

The extractor covers classes/bases, sync/async functions, immediate class methods,
nested declarations, parameter names/kinds/annotations/default-presence, decorator
names, direct/annotated/unpacking module assignments, imports and call syntax.
Definition parent IDs and exact locations support future module/finding mapping.
Simple prior same-scope local base classes can link to class IDs; imported or
dynamic base expressions are retained without pretending to resolve a runtime type.

Framework imports and direct FastAPI/APIRouter/Flask/Blueprint construction are
explicit indicators. Routes on those locally bound objects preserve their symbol,
receiver, declared supported HTTP methods and decorator locations. Route path
literals are always redacted; `path_is_literal` describes a positional string
argument only. Supported helpers are get/post/put/patch/delete/head/options/
websocket, route and api_route. Imported app instances, factories/wrappers,
arbitrary object alias propagation and computed registrations are not resolved.

Classifications can be multiple and are not enforced architectural layers:
explicit routes imply a controller/route-handler role; explicit DB APIs imply
data access; recognized ORM base declarations indicate database-modeling code;
environment APIs indicate configuration; auth imports indicate authentication-related
code. These are confirmed **static indicators**, not runtime behavior, mapped
table existence, authentication coverage or deployment guarantees. Filename/path
tokens infer service, controller, repository/data-access, model, auth, configuration,
utility and test roles. Inferred roles are labeled as such; explicit evidence
takes priority for the same module/component. No layered architecture is assumed.

Calls are syntactic observations, not resolved invocation edges. Names/attribute
chains may be retained with candidate visible import qualification; parameter
shadowing and simple reassignment are handled, but full Python binding/type
semantics are not. Subscripted/dynamic callables and dynamic imports remain
unresolved. Lambdas/comprehensions are not exported as named functions, and
assignment metadata excludes class attributes and runtime mutation.

No defaults, assignment values, call arguments, annotation-string values, route
paths, docstrings or comments are returned. Identifier and relative file names
are intentionally retained for navigation. Access to raw source context remains
a separate backend responsibility with authorization and redaction controls.

## Commands and verification

Run from a trusted checkout, with the existing security environment:

```powershell
python -m backend.app.analyzers.structure_cli fixtures/structure_demo
python -m backend.app.analyzers.structure_cli REPOSITORY --max-files 2000 --max-repository-bytes 20971520
python -m pytest backend/tests/test_structure_analyzer.py -q
$env:CODELY_RUN_SEMGREP_INTEGRATION = "1"
python -m pytest -q
```

The structure CLI requires no scanner/network and exits 0 for complete supported
file extraction, 2 for partial/error. The intentionally malformed demo exits 2
and still returns usable JSON. Existing scanner/checklist CLIs are unchanged.

Observed on native Windows/Python 3.11.9: **61 new AST tests pass; 210 total tests
pass**, including all 19 real native Semgrep/checklist integration tests. New tests
are direct AST/file analyses, not scanner mocks. Permission/link escape branches
use controlled mocks to exercise safe rejection without changing OS permissions.
The actual shared checkout smoke analysis discovered 82 Python files, parsed 81,
and truthfully reported partial coverage for the intentionally broken fixture;
its full metadata is locally saved in ignored `.semgrep-local/phase4-shared-repository.json`.
No target source, setup.py, tests, route, import hook or Docker instruction ran.

Phase 5 can later aggregate these import records into React Flow/NetworkX nodes
and edges, preserve all source evidence and traverse incoming dependencies. This
release adds neither that graph nor impact/cycle/rule analysis. The existing
architecture hook is deliberately not pointed at this richer structure contract.

Phase 5 now consumes this unchanged structure interface through
`architecture_graph.build_architecture_graph(structure)`. See
ARCHITECTURE_INTEGRATION.md for graph/traversal contracts and limits.

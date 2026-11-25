# Architectural Security Impact Mapping v1.0.0

ASIM connects original security findings to parsed source and existing architecture
nodes. Reverse import traversal identifies **potentially relevant dependent modules**,
not confirmed exploit propagation. Severity and CWE remain properties of the original
finding. No dependent module is assigned that finding or a derived security score.

Phase 5 was verified at local/remote commit `662ddaa` with a clean tree and a
281-test passing report. Phase 6 adds independent modules/contracts and preserves
the scanner, checklist, AST, graph and CodeRAG source provenance.

## Public interfaces and reuse

```python
from backend.app.analyzers.semgrep_adapter import scan_repository
from backend.app.analyzers.structure_analyzer import analyze_repository
from backend.app.analyzers.architecture_graph import build_architecture_graph
from backend.app.analyzers.impact_analyzer import (
    ImpactOptions, analyze_security_impact, analyze_finding_impact,
)

scan = scan_repository(validated_repository_path)
structure = analyze_repository(validated_repository_path)
architecture = build_architecture_graph(structure)
impact = analyze_security_impact(scan, structure, architecture)
payload = impact.to_dict()

single = analyze_finding_impact(finding_id, scan, structure, architecture)
package = impact.evidence_for_finding(finding_id)
```

Reuse already available inputs rather than running those stages again. The mapper
and evidence-package helpers never scan, parse, build a graph or read target files.
The explicit CLI below runs each pipeline stage once. The scan may be ScanResult
or its dictionary envelope; structure/architecture must be their trusted in-memory
objects. From backend/, use `app.analyzers...` imports consistently instead.

Pass the original full scanner result before backend conversion to a findings-only
model: status/process/diagnostics are needed to assess coverage. Missing or invalid
scan coverage is never interpreted as a completed clean scan. Positive findings
can still be mapped under partial scanner coverage, with overall partial status.
A failed empty scan returns error, not a successful zero-impact report.

All inputs must refer to the **same immutable repository version**. The engine
checks graph/module IDs, paths, parsed states, source-module counts and every
existing graph import reference against the supplied structure. Incompatible
references fail closed. These checks do not prove that an old scan and new source
are the same content: existing contracts have no shared content fingerprint.
The backend owner must bind inputs to its project/repository-version cache and
prevent mutation across the pipeline. `snapshot_identity=caller_required` makes
this boundary explicit. Project/scan/version IDs can wrap the impact payload;
they are not invented or added to the unchanged finding contract.

## Mapping and interpretation

Each normalized finding retains its ID, rule ID, source, severity, CWE and normalized
relative file/line location in a new nontext metadata object. Windows separators
are accepted; absolute, UNC, drive-relative and escaping finding paths are rejected
without echoing unsafe paths. File spelling/case must match the repository.

Mapping requires a parsed file with a valid line range and an existing graph node.
The existing AST helpers identify the innermost function/method/class that encloses
the full finding range. Module scope is an explicit fallback, not an invented
function. Symbol descriptors retain stable IDs, qualified names and source bounds;
source references include decorator extents when relevant.

Findings that cannot map remain in finding_impacts with mapping_status=unmapped
and an explicit reason: missing source, unparsed source, invalid/out-of-range
location, missing graph node, invalid metadata, duplicate finding ID, input mismatch
or configured analysis budget. Nothing silently disappears. Duplicate IDs remain
separate records and are marked ambiguous. Invalid IDs can be null; distinct impact
record IDs and summary counts still preserve those input entries. `id` identifies
the impact record; `finding_id` identifies the original scanner finding.

Source module, direct dependent and transitive dependent are distinct roles relative
to each finding. A module can contain its own independent finding and also be a
dependent for another finding; this does not copy either vulnerability between them.
An importing module may never call the vulnerable function. Conditional/function-local
imports and unknown runtime state remain limitations of the underlying graph.

## Result shape and graph compatibility

`contracts/security-impact-v1.schema.json` defines the separate ASIM v1 contract.
Existing finding/structure/graph schemas are unchanged. The normalized payload has:

- finding_impacts: original finding metadata, mapping result, vulnerable node ID,
  enclosing symbols, source references, direct/transitive dependent IDs, relevant
  edge IDs, evidence path IDs, module_impact_id and per-finding truncation diagnostics.
- module_impacts: one cached dependency analysis per analyzed vulnerable module,
  shared by every finding in that module. Includes dependency distances, exposure
  roles, bounded evidence paths, edge IDs, counts and traversal coverage.
- node_contexts: existing graph IDs, labels, module files, architectural roles and
  their confirmed/inferred static classification evidence. No propagated severity.
- evidence_edges: original architecture edge IDs and source/target pairs, with
  selected supporting import locations and explicit evidence truncation counts.
- summary, diagnostics and coverage: actual mapping counts, source states,
  unresolved/ambiguous import counts, limits and interpretation restrictions.

Module analysis is cached within one invocation; no redundant traversal is performed
for several findings in the same module. Distances/path objects live in the shared
module table to avoid repeating large evidence arrays for every finding. The
evidence_for_finding helper expands the selected references into a self-contained
metadata package. For duplicate IDs use evidence_for_result(impact_record_id);
evidence_for_finding rejects ambiguous selection. A missing requested ID yields
an error result in single-finding analysis rather than a completed empty report.

## Dependency paths and limits

Graph arrows stay **importer -> imported module**. From a finding in database D,
reverse traversal can reach service S and controller C; the proof path is
`C -> S -> D`. Distances count observed import edges, not calls or exploit hops.
The existing bounded reverse traversal supplies reachable modules and primary
shortest paths. Additional alternatives follow strictly decreasing distance,
forming a path DAG even when the original import graph has cycles.

ASIM returns multiple shortest paths where static evidence and budgets allow it.
It does not enumerate every simple path or longer alternative path. The vulnerable
seed is excluded from dependent lists, including circular/self-import scenarios.
Outgoing dependencies of an importer are not automatically upstream dependents
of the finding source (for example, an authentication library imported by a
controller is not necessarily dependent on its database module).

ImpactOptions defaults:

| Budget | Default |
| --- | --- |
| traversal depth | 32, configurable 0..256 |
| visited nodes per module, including source | 1,000 |
| traversal examined edges per module | 10,000 |
| returned shortest paths per module | 128 |
| selected finding records attempted | 1,000 |
| distinct module analyses | 128 |
| extra shortest-path edge search | 10,000 per module |
| extra path expansions | 10,000 per module |
| exported evidence per edge | 32 import records |
| exported evidence total | 10,000 import records |
| input diagnostics exported | 100 |

```python
from backend.app.analyzers.architecture_traversal import TraversalLimits

options = ImpactOptions(
    traversal=TraversalLimits(max_depth=4, max_nodes=100, max_edges=1000, max_paths=50),
    max_findings=500,
)
impact = analyze_security_impact(scan, structure, architecture, options=options)
```

Limitations are explicit at root, module and finding level. Finding-budget overflow
retains unmapped rows with max_findings. Module-budget overflow can retain valid
source mapping with no dependency analysis, marked truncated. Exported edge evidence
can be incomplete even when reachability was computed; evidence_count versus
provided_evidence_count and evidence_truncated show this. Paths with missing exported
proof still refer to the unchanged full graph's edge IDs. Empty arrays under partial,
unmapped or truncated coverage must not be rendered as proof of no dependent modules.

complete means all selected findings mapped within declared scope/budgets and all
input coverage is complete. Unresolved or ambiguous imports make ASIM partial even
when the graph builder successfully built its resolved subset. Namespace-only
imports and unparsed modules are counted explicitly. Invalid/incompatible inputs
can return error; known positive mappings remain inspectable when appropriate.
Diagnostics contain sanitized codes/relative references, including informational
scanner diagnostics; nonempty diagnostics alone is not a failure test. Use status
and coverage. No state means that the application is secure.

## Frontend highlighting

Keep the existing architecture payload and its node/edge IDs. For the selected
finding row, use vulnerable_node_id for the source highlight, direct_dependent_node_ids
for direct relevance and transitive_dependent_node_ids for indirect relevance.
Use relevant_edge_ids/evidence_path_ids to highlight existing relationships; resolve
module_impact_id to get distances and paths. No graph reconstruction is needed.

Style dependents as **potential dependency relevance**, not additional vulnerabilities.
Show original severity only with the original finding/source. Preserve graph
classification confidence and all partial/unmapped/truncated states. In a repository
overview a node may legitimately be both another finding's source and a dependent;
display its independently detected findings rather than propagating severity.
The engine does not add React components, layout, routes or backend response models.

## Gemini evidence consumption

`impact.evidence_for_finding(finding_id)` returns selected original metadata,
source references, enclosing symbols, shared dependency analysis, architectural
classifications, import evidence, coverage and interpretation guidance. This is
data for the existing GenAI team, not a model call or prompt-execution engine.

Finding title/message and arbitrary extra scanner evidence are intentionally **not
forwarded**, because those strings can contain source or secret values. IDs,
rule/source identifiers, severity, CWE and safe locations are retained. The input
ScanResult is never modified. No source snippets, SQL strings, credentials,
docstrings, raw errors or environment values are read/exported by ASIM. Identifier
and relative filename metadata remains visible for navigation.

If explanations need prose rule descriptions or code snippets, the backend/GenAI
owner can resolve the trusted local rule catalog and retrieve narrowly authorized,
redacted source spans through its existing source-access boundary. Preserve input
repository version, coverage and uncertainty. Static paths support explanations
of potential relevance; they do not justify claims of confirmed exploit spread,
exploitability probabilities or security/architecture scores.

## Actual demonstration and tests

The seven-file `fixtures/impact_demo/` is never imported or executed. It contains
a Flask application, blueprint route, authentication wrapper, service, database
class, unrelated module and circular service/helper imports. One real native
Semgrep scan detects `codely.python.sql-injection`, HIGH/CWE-89, at database.py:11.
AST maps it to Repository.lookup within Repository. The graph has seven nodes,
six import edges and one cyclic component. ASIM returns:

- mapped findings: 1; unmapped findings: 0
- direct dependent: services.py, distance 1
- transitive dependents: api.py and cycle.py, distance 2; app.py, distance 3
- four shortest paths with four distinct supporting edges
- unrelated.py and auth.py excluded from this finding's dependent set

`contracts/examples/security-impact-v1.json` is that actual result, validated
against the schema and compared exactly with fresh native pipeline output.
The example is not fabricated expected product data. It contains no source text.

```powershell
# Explicit one-pass convenience pipeline; requires working native Semgrep.
python -m backend.app.analyzers.impact_cli fixtures/impact_demo
# Unit/static ASIM tests use supplied synthetic normalized findings and actual AST.
python -m pytest backend/tests/test_impact_analyzer.py -q
# Full suite including real scanner pipelines outside the restricted sandbox.
$env:CODELY_RUN_SEMGREP_INTEGRATION = "1"
python -m pytest -q
```

CLI exit 0 means complete scoped impact analysis, even with original vulnerabilities;
exit 2 means partial/error. An original vulnerability is not converted to a new
vulnerability for each dependent. Native test opt-in is still required in Codex
because the Windows scanner core fails at socketpair inside the restricted sandbox.

Actual final verification on Windows/Python 3.11.9: **342 passed**. This is 320
unit/static tests (including 58 new ASIM tests) and 22 tests backed by real native
scans (including three new end-to-end tests sharing one actual fixture pipeline).
The native tests cover mapping, exact dependents/cycle handling, schema and the
generated example. Unit tests do not claim native vulnerability detection; they
cover mapping, malformed/unmapped/duplicate inputs, shortest-path alternatives,
cache reuse, multiple sources, limits, stale-reference rejection, missing coverage,
Windows paths, redaction, deterministic output and no implicit pipeline reruns.

Previous scanner/checklist/AST/graph behavior and contracts are preserved. The
teammate backend still needs explicit API/metadata wiring by its owner; no Gemini
module was duplicated or modified. Phase 7 rules/optimizations are not implemented.

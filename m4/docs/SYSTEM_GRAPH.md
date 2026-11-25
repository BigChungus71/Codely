# System graph handoff

Call `m4.ai_intelligence.system_graph.analyze_system(project_path)` after validating a configured checkout root. Install `m4/requirements-parsers.txt` for the Java/TypeScript/JavaScript parsers. No target code is executed, imported, built or uploaded. The existing Python dependency graph and M4 advice interfaces are independent of this analyzer.

The result matches [system-architecture-v1](../contracts/system-architecture-v1.schema.json). It has `graph_type: system`, status, nodes, evidence-backed directed edges, diagnostics and coverage. Node `file` is the primary evidence path and `files` contains additional paths. Edge `file` and line fields provide the existing UI anchor while `evidence` retains all selected anchors. Paths are repository-relative. IDs derive from canonical component and relationship identities. Outcomes are `complete`, `partial`, `unsupported` and `error`.

- Spring roles come from recognized Spring annotations and explicit JPA repository types. Declared field and constructor references are structural evidence, not runtime calls or proof of injection.
- React is identified by its package manifest. Source paths group frontend modules by feature. Resolved relative imports connect modules. Router, state and API-client usage are evidence-backed module capabilities rather than deployments.
- Maven JPA/JDBC/Redis, Mail and selected Spring AI dependencies represent configured capabilities, not live external services.
- API edges connect a literal frontend request or simple local constant to the longest uniquely matching Spring annotation prefix. These edges are inferred. Ambiguous or unresolved routes produce diagnostics. Dynamic routing, aliased HTTP clients, path-alias import resolution and runtime connectivity are outside scope.
- The inventory and graph are bounded. Diagnostics report truncation, parser availability and parse failures. Unsupported repositories do not produce invented graph elements.

The local VoiceAIAgentPro checkout produced a partial graph with 50 nodes and 140 edges. It identified 4 controllers, 18 services, 3 repositories, 9 components, 4 configuration areas, 8 grouped frontend modules, the frontend/backend apps and 2 declared integrations. The 140 edges included 2 inferred frontend route links. It parsed 103 Java, 76 TypeScript and 68 JavaScript-family files. One source could not be parsed. Counts reflect the unmodified local working checkout.

With the optional parsers installed, `PYTHONPATH=m4 python -m pytest m4/tests --ignore=m4/tests/fixtures -q` passed 54 tests and 38 subtests. Tests exercise source paths and lines, stable node IDs, non-dangling edges, renderable evidence, unsupported behavior, classes and constructor dependencies, React grouping and route provenance.

Backend integration should dispatch `GET /api/projects/{project_id}/architecture?view=system` to this analyzer and preserve the existing dependency view as the default. Forward the full evidence and coverage, validate paths and endpoints, and render partial status separately from provider/service errors.

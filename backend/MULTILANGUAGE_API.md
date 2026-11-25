# Multi-language API compatibility

Install the scanner and architecture feature code alongside this service to enable both views. Set `CODELY_SCANNER_ADAPTER=backend.app.analyzers.backend_adapter:scan_repository` for the bundled rules and `CODELY_SYSTEM_ARCHITECTURE_ADAPTER=m4.ai_intelligence.system_graph:analyze_system` if an explicit hook is preferred. Keep the repository root on PYTHONPATH. Install the scanner's pinned Semgrep and the architecture branch's optional parser requirements. The system adapter is discovered automatically when its module is importable.

Completed scan and findings responses carry nullable `coverage` and optional diagnostics. Findings keep their existing fields. Partial/failed, timeout and unsupported results remain non-success HTTP responses and can carry observed coverage and any validated partial findings in `detail`. Unsupported language returns HTTP 422 and timeout returns 504. A failed response never replaces a completed cache entry.

`GET /api/projects/{project_id}/architecture` keeps the default dependency hook. Add `?view=system` for the Java/React graph. Responses include the view, status, source anchors, coverage, evidence and confidence. Unsupported graph requests return 422, and absent analyzers return 503. The API checks component and edge IDs, edge endpoints, existing relative source paths and one-based source ranges.

When integrating, apply the coverage DTO and failure mapping to the existing integration scanner adapter and keep its fixtures, version binding, and M3/M4 services. The existing integration dependency graph should remain the default. Its static impact mapper is Python-only, so restrict impact to Python findings when the scanner adds Java and web results.

Verification on the backend feature branch passed 14 API tests. With the two feature analyzers on PYTHONPATH, native VoiceAIAgentPro scanning returned HTTP 200 with 251 scanned files and 23 findings. The system graph returned HTTP 200, partial coverage, 50 nodes and 140 edges.

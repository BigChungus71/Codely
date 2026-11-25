# Security and Code Intelligence

Preserve the shared finding contract and deterministic local analysis. Never execute
analyzed source, install its dependencies, download remote rules, or expose secrets.
Use bounded subprocesses and report partial coverage and scanner failures. No API,
frontend, Gemini, or architecture work is authorized. The current user authorizes
migration plus the Phase 3 checklist only, with commits/pushes exclusively to
security-analysis. Never force-push or modify main. Preserve teammate code.

See SECURITY_README.md, CODERAG_INTEGRATION.md, and SETUP_REPORT.md at repository
root for scanner instructions and verification. Native tests require
CODELY_RUN_SEMGREP_INTEGRATION=1 outside the restricted sandbox.

Checklist v1.0.0 is in app/checklists. Its evaluator must reuse the provided
current-version scanner result, preserve uncertainty, and never emit source or
secret values. See CHECKLIST_INTEGRATION.md. Stop before Phase 4.

The user subsequently authorized Phase 4 AST structure analysis, committed and
pushed only to security-analysis. Its interface is structure_analyzer.analyze_repository,
with a separate repository-structure-v1 contract. Never execute/import target code
or emit literal values. Preserve unresolved/ambiguous evidence and classify
heuristics as inferred. See STRUCTURE_INTEGRATION.md. Stop before Phase 5; no
full graph, impact mapping, architecture adapter, API/frontend or Gemini work.

The user subsequently authorized Phase 5 architecture dependency graphs using
existing NetworkX and RepositoryStructure. Graph edges must be importer -> imported
with all supporting evidence; no fabricated unresolved edges or runtime-call claims.
Preserve confidence/coverage and bound traversal. See ARCHITECTURE_INTEGRATION.md.
Commit/push only security-analysis. Stop before the complete Phase 6 impact mapper;
no API/frontend/Gemini work or metric-only architecture quality verdicts.

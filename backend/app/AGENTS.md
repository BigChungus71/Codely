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

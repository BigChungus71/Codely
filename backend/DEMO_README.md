# Codely backend demonstration

Run from this backend directory (Python 3.10+):

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-demo.txt
cp .env.example .env
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/docs. The default repository is `../../VoiceAIAgentPro`, resolved relative to this backend directory. Override `VOICE_AI_AGENT_PATH` in `.env` if needed. No Gemini key, FAISS index, scanner, or graph service is needed to start and browse. Existing CodeRAG routes remain registered; install `requirements.txt` and configure Gemini to use their original analysis services. Missing legacy libraries return 503.

## Demo flow

1. `GET /api/projects`
2. `GET /api/projects/voice-ai-agent/tree`
3. `GET /api/projects/voice-ai-agent/files?path=backend/pom.xml`
4. `POST /api/projects/voice-ai-agent/scan`
5. `GET /api/projects/voice-ai-agent/findings`
6. `POST /api/projects/voice-ai-agent/findings/{finding_id}/explain`
7. `GET /api/projects/voice-ai-agent/architecture`

Project listing returns 503 if the configured checkout is missing. Unknown IDs return 404. Source access rejects traversal/symlinks (403), missing files (404), files over 512 KB (413), and unsupported/binary/non-UTF-8 files (415). Hidden files and generated directories are excluded. Source browsing deliberately uses an extension allowlist.

Scans are synchronous. A process-local lock returns 409 for concurrent scans; no task queue is required. Use one Uvicorn worker: the memory cache is per process and resets on restart. Completed scans include `repository_version`, `scanned_at`, and `cached`; repeat requests use the cache only for identical repository bytes. Failed or partial scans are never cached. The hash includes regular files under nonhidden, nonexcluded directories; `.git`, dependencies, build outputs, and symlinks are outside this content version. Findings return `not_scanned` or `stale` with an empty list when no current scan exists. The UI must distinguish these states from `completed` with zero findings. Scans and explanations reject edits during analysis with 409. No results are persisted.

## Member 3: scanner and architecture hooks

Configure importable synchronous callables using `module:function`:

```dotenv
CODELY_SCANNER_ADAPTER=team_security:scan_repository
CODELY_ARCHITECTURE_ADAPTER=team_architecture:analyze_repository
```

Scanner signature: `scan_repository(project_path: str) -> dict`. Return `{"findings": [...], "errors": []}` matching `codely/schemas.py`. Include real scanner evidence in each finding's `evidence` object. IDs must be unique, file paths relative, line numbers one-based and inclusive, severity one of CRITICAL/HIGH/MEDIUM/LOW/INFO/UNKNOWN. Nonempty errors mean incomplete analysis and produce 502. File locations are checked against the real source.

Alternatively install Semgrep in the same environment and set `SEMGREP_CONFIG` to Member 3's local rule file or a chosen registry config. The included CLI adapter runs Semgrep with JSON output, strict errors, disabled metrics, and a 90-second process timeout. It normalizes ERROR/WARNING/INFO to HIGH/MEDIUM/INFO while preserving the original finding. No rule pack or vulnerable fixture is invented here. Semgrep is optional and has not been installed or run in this checkout.

Architecture signature: `analyze_repository(project_path: str) -> dict` with `nodes` and `edges` matching the schemas. Nodes require real relative source paths; edges must reference existing node IDs. The analyzer owns evidence that a relationship is observed; the API validates shape, paths, and references, not semantic correctness. No graph inference or AI recommendations are fabricated. Without a hook this route returns 503.

Hooks must bound their own I/O and computation (scanner <=90 seconds, explanation <=45 seconds recommended). Trusted Python hooks execute inside the API process; the API cannot forcibly cancel a hung custom callable. The built-in subprocess and Gemini calls have explicit timeouts.

## Member 4: Gemini hook

```dotenv
CODELY_EXPLANATION_ADAPTER=team_gemini:explain_finding
```

Signature: `explain_finding(finding: dict, context: dict) -> dict`, matching `Explanation` in `codely/schemas.py`. Context contains `file`, one-based `start_line`, and `content`. It is limited to a nearby excerpt, at most 101 lines and 16,000 characters; raw scanner output is excluded from the prompt. Return the same finding ID, nonempty explanation/impact/recommendation, optional suggested code, and `requires_developer_review: true`. Invalid responses return 502. A current scan is required (409 otherwise); unknown findings return 404. Scanner results remain available if Gemini fails.

Without the hook, install `google-generativeai`, set `GEMINI_API_KEY`, and optionally `GEMINI_MODEL` to use the existing CodeRAG SDK infrastructure with structured output and a 45-second request timeout. No explanation has been verified against live Gemini here. No key is stored or returned. SDK/provider/validation failures are explicit errors, with no canned explanation fallback.

## Verification and current state

```sh
.venv/bin/python -m pytest tests -q
```

12 focused tests passed: startup/legacy route registration, real file semantics, exclusions, traversal, symlinks, binary and oversized files, missing projects, unavailable services, adapter schemas, empty scans, incomplete scans, caching, stale results, concurrent edits, explanation context, graph references, Semgrep normalization and timeout. External scanner/provider behavior is stubbed only inside tests. A Starlette TestClient deprecation warning is nonblocking.

Against the actual VoiceAIAgentPro checkout: health, projects, tree (296 browsable files at verification), and `backend/pom.xml` all returned 200. Findings correctly returned `not_scanned`; scan and architecture returned 503. No real findings, Gemini explanations, or graph have been generated. Live Uvicorn HTTP checks also returned 200 for health, listing, tree, and source retrieval; the verification server was then stopped. No source in VoiceAIAgentPro was modified. Its existing uncommitted work remains intact.

Full demo blockers: Member 3 scanner/rules and architecture adapter, Member 4 explanation adapter or configured Gemini SDK/key, and at least one real finding if the finding-explanation segment is required. If the real target is clean, use a separate clearly labeled fixture rather than altering its source. API samples are in `API_EXAMPLES.md`; interactive typed contracts are at `/docs` and `/openapi.json`.

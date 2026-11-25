# Codely cross-branch integration report

The integration uses the complete Next.js workspace as its base. The frontend root is `566d37e5904488f2fd51b9e3ba1bb2959ea2e16e`. Main, M2, M3, and M4 share root `db751a7b46a541630310a281aa014774f714018b`. There is no merge base between those histories and the frontend. The [ledger](INTEGRATION_LEDGER.md) records exact source revisions and integration methods.

| Branch inspected | Tip time in IST | Implementation, dependencies and tests |
| --- | --- | --- |
| `main` | 13:24:52 | CodeRAG backend and extension ZIPs. No unified app. |
| `feat/frontend-workspace` | 15:00:24 | Next.js 16, React 19, BoardUI, frontend TypeScript and AI SDK streaming chat. Latest changes center the chat layout. Scanner was timer based and dashboard metrics were demo estimates. |
| `feature/backend-core` | 13:54:38 | FastAPI/Pydantic backend, typed adapter, path-safe repository access, content-version cache, API smoke tests. Legacy optional CodeRAG routes use Gemini, FAISS and document processing. |
| `feature/security-analysis` | 14:03:40 | Semgrep 1.187.0, trusted Python rules, normalized evidence and failures, fixture tests. Includes duplicate CodeRAG reference files. |
| `security-analysis` | 14:53:21 | Extends the scanner branch with an evidence checklist, Python AST inspection, internal imports, coverage diagnostics, schemas and tests. |
| `feature/ai-intelligence` | 15:07:56 | M4 REST Gemini and optional Groq providers, structured review and architecture advice, redacted retrieval, optional FAISS/local embeddings, provider and grounding tests. |

All times are 25 November 2026. M2 supplies the one FastAPI application. The M3 import omitted its duplicate CodeRAG reference copy and preserved scanner, checklist and AST implementations. A representative AST test now checks the executing parser version independently of its fixture snapshot. The fixture remains intact. M4 supplies the finding review service and retrieval index. Markdown and text documents are included for system-design retrieval. The analysis UI reuses the typed client and stopped incrementing synthetic dashboard metrics when scans run.

| Backend contract | Consumer and behavior |
| --- | --- |
| `GET /api/health` | Runbook and smoke checks. Legacy `/health` remains available. |
| `GET /api/projects` | Scanner project selector. VoiceAIAgentPro appears when its checkout is available. The Python fixture is separately labeled. |
| `GET /api/projects/{project_id}/tree` and `GET …/files?path=…` | Repository explorer and finding/graph source navigation. Numbered read-only source view. |
| `POST /api/projects/{project_id}/scan` and `GET …/findings` | Scanner displays the completed scan payload. Findings API retrieves the same versioned results. M3 diagnostics survive mapping, and failures are separate from successful empty scans. |
| `POST /api/projects/{project_id}/findings/{finding_id}/explain` | Expanded finding actions. M4 maps source-grounded review into the existing response with optional assumptions and limitations. |
| `GET /api/projects/{project_id}/architecture` | Module/import view. Edges link to the recorded import line. Incomplete parser coverage is visible. |
| `POST /api/projects/{project_id}/design-question` | Next.js `POST /api/chat` uses it for project chat and converts the structured answer to the existing AI SDK stream format. Source citations populate the answer. Plain chat continues on its existing provider path. |

The app uses ports 3000 and 8000 by default. Browser requests use the public backend URL. Next forwards project chat from its server using a separate backend URL. Live Gemini or Groq calls require explicit opt-in and their server-side key. Project chat sends the latest question, including constraints written in that question. The structured endpoint also accepts a separate constraints field. Retrieval uses lexical matching over the M4 repository index, including Markdown/text documents. Optional semantic embeddings and M4's graph-patch recommendation mode remain standalone.

Verification covered native Semgrep and AST suites, frontend TypeScript, the client contract, and a local Chrome run with real FastAPI and Next.js. Chrome verified repository selection, real source, the two rule findings from the existing synthetic Python project, source navigation, architecture output, and unavailable-AI behavior through explanation and chat. The real VoiceAIAgentPro Maven file also returned 200. Provider tests exercise isolated contracts and the design retrieval test uses a stub provider. No live Gemini output was verified.

Remaining scope: M3's integrated scan and graph are Python-only. VoiceAIAgentPro's Java and TypeScript sources are browsable; analysis coverage does not include those languages. The dashboard retains its existing illustrative counters. The checklist is tested as a service and has no dashboard consumer. The source viewer does not use Monaco. Project selection supports server-configured checkouts. Arbitrary uploads/cloning and architecture comparison are outside the integrated UI.

| Verification command | Result |
| --- | --- |
| `PYTHONPATH=.:backend:m4 CODELY_RUN_SEMGREP_INTEGRATION=1 python -m pytest backend/tests m4/tests -q` | 241 passed, 1 optional extra-language parser test skipped, 7 subtests passed. |
| `npm run typecheck` | Passed. |
| `node --experimental-strip-types --test integrations/frontend/codely-client.test.mjs` | 4 passed. |
| Local Next/Uvicorn and Playwright Chrome smoke | Passed. Both servers stopped after the check. |

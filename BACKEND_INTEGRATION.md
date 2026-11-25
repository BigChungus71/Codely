# Backend and frontend compatibility

Backend source lives in `backend/`; start with [backend/DEMO_README.md](backend/DEMO_README.md). API response samples are in [backend/API_EXAMPLES.md](backend/API_EXAMPLES.md). The original ZIP archives on main remain unchanged. VoiceAIAgentPro is an external read-only checkout and is not committed.

## Run locally

```sh
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-demo.txt
cp .env.example .env
# Set VOICE_AI_AGENT_PATH if the demo checkout is not at ../../VoiceAIAgentPro.
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/docs. Browser requests from the Next.js app on port 3000 are supported by existing CORS middleware. Do not send credentials or keys in browser requests. Use one backend worker for the in-memory cache; Docker/Procfile defaults are adjusted accordingly.

## Frontend checked

The actual branch is **`feat/frontend-workspace`**, at `d37b6afbc0cfceadae9f0074dcaffc7e318dc5e8` (there is no remote `feature/frontend-workspace` branch at verification time).

| Area | Observed frontend behavior | Backend compatibility |
| --- | --- | --- |
| Scan trigger | `scanner-panel.tsx` uses a timer and `DEMO_FINDINGS` | Not connected; replace the timer with the provided client |
| Finding display | lowercase severity, `description`, `line` | Adapter maps backend severity, `message`, `start_line` |
| UNKNOWN severity | No unknown enum in UI | Adapter uses info presentation and visibly prefixes original UNKNOWN severity; original retained in `scannerSeverity` |
| Empty results | UI renders "No issues found" for an empty array | Only pass `completed` results; helper rejects `stale` / `not_scanned` |
| Input | File upload or arbitrary GitHub URL | Unsupported by this demo backend; select the configured project instead |
| Options | Dependency audit, architecture comparison, baseline selection | No backend support; do not claim these switches affect `/scan` |
| Architecture | No graph API consumer found in scanner | Backend endpoint waits for Member 3's analyzer |
| AI chat | Next.js `/api/chat` uses its own AI SDK streaming protocol | Separate from structured finding explanation; no chat compatibility claim |
| Browser origin | Next.js on 3000, FastAPI on 8000 | CORS preflight tested |

The frontend is **compatible at the display/type level through the adapter, but is not end-to-end wired**. Its existing demo data and dashboard/chat behavior were not rewritten or represented as real scanner results.

## Typed adapter

`integrations/frontend/codely-client.ts` has no runtime dependencies. It covers all seven backend endpoints and preserves HTTP errors. Import it from the merged frontend (or copy it into your app):

```ts
import { createCodelyClient, completedFindings } from "@/integrations/frontend/codely-client";

const api = createCodelyClient(process.env.NEXT_PUBLIC_CODELY_API_URL ?? "http://localhost:8000");
const result = await api.scan("voice-ai-agent");
// Call setFindings only after success. On error, show an error state instead of clean results.
setFindings(completedFindings(result));
```

Add `NEXT_PUBLIC_CODELY_API_URL=http://localhost:8000` to the frontend's `.env.local`. This is a public service URL, never an API key. The input selector must use `api.projects()`; uploads and arbitrary cloning are intentionally outside this backend's scope. Persist `repository_version`/`scanned_at` in the UI if displaying cache provenance. Explanation calls require the current finding ID from real completed results.

## Git integration

`feature/backend-core` is based on the target repository's existing **main** history. The frontend branch and main have **unrelated Git roots** (verified with `git merge-base` and root commits), so an ordinary branch merge cannot combine them. This is an existing repository-history issue.

All backend changes are additive under `backend/`, `integrations/frontend/`, `.github/workflows/backend.yml`, and this document. The single backend commit can be cherry-picked onto the frontend branch without importing the unrelated history:

```sh
git fetch origin
git switch feat/frontend-workspace
git cherry-pick origin/main..origin/feature/backend-core
```

Do this on the frontend integration branch when ready; no push to the existing frontend branch or main was performed. A direct PR into main contains backend code only. A PR into the frontend branch would need shared history first. No forced push is needed.

## Verification

- Python smoke tests: 12 passed, including cross-origin POST preflight.
- Node adapter contract tests: 4 passed, covering every route/method, finding mapping, stale/empty distinctions, and HTTP 503 propagation. These tests stub HTTP responses; they do not claim external scanner availability.
- Actual frontend `npm ci --ignore-scripts --no-audit --no-fund` and `npm run typecheck` passed.
- The adapter compiled with the actual frontend `ScanFinding` type and strict project settings.
- Combined-tree verification: the backend commit cherry-picked onto the actual frontend checkout without conflicts, and `npm run typecheck` passed again.
- Real project listing, file browsing and source retrieval work. Scanning, architecture, and Gemini still require teammate implementations/configuration; no findings or explanations were fabricated.

The new GitHub Actions workflow repeats backend and adapter tests. Hosted workflow execution is not claimed until GitHub runs it.

# Frontend API examples

Base URL: `http://127.0.0.1:8000`. All errors use `{"detail":"..."}`. All paths below are relative to that base. Full field types and required fields are in `/openapi.json`. No endpoint contract was removed.

## Project listing — GET /api/projects

Observed on the real checkout:

```json
{"projects":[{"project_id":"voice-ai-agent","name":"VoiceAIAgentPro","status":"ready","languages":["css","html","java","javascript","json","markdown","properties","python","shell","sql","text","typescript","xml"]}]}
```

## Tree — GET /api/projects/voice-ai-agent/tree

Abbreviated example of actual repository structure; the API returns the full source tree:

```json
{"project_id":"voice-ai-agent","tree":[{"name":"backend","path":"backend","type":"directory","children":[{"name":"pom.xml","path":"backend/pom.xml","type":"file"}]}]}
```

Directories have `children`; files omit `children`.

## Source — GET /api/projects/voice-ai-agent/files?path=backend/pom.xml

Abbreviated content example; the API returns the actual complete file:

```json
{"project_id":"voice-ai-agent","path":"backend/pom.xml","language":"xml","content":"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n..."}
```

## Findings — POST scan / GET findings

`POST /api/projects/voice-ai-agent/scan` and `GET /api/projects/voice-ai-agent/findings` share a response schema. Before the first completed scan:

```json
{"project_id":"voice-ai-agent","status":"not_scanned","repository_version":"<SHA-256 of actual repository bytes>","cached":false,"scanned_at":null,"findings":[]}
```

**Contract illustration only, not a finding observed in VoiceAIAgentPro:**

```json
{"project_id":"voice-ai-agent","status":"completed","repository_version":"<repository SHA-256>","cached":false,"scanned_at":"2026-11-25T08:00:00+00:00","findings":[{"id":"<stable scanner finding ID>","rule_id":"<actual scanner rule>","source":"semgrep","severity":"HIGH","title":"<scanner title>","file":"<actual relative source path>","start_line":25,"end_line":28,"message":"<actual scanner message>","cwe":[],"evidence":{}}]}
```

Successful clean scans use `status: completed` and `findings: []`. Cached results retain the original `scanned_at` and use `cached: true`. Modified files yield `status: stale` and no displayed findings until a new scan. Unavailable scanner: HTTP 503. Scanner failure/partial analysis: 502. Timeout: 504. Concurrent scan or changed repository: 409.

## Explanation — POST /api/projects/voice-ai-agent/findings/{finding_id}/explain

No request body. **Schema illustration only; these placeholders are never served as explanations:**

```json
{"finding_id":"<selected finding ID>","status":"completed","explanation":"<provider explanation grounded in source>","potential_impact":"<provider impact assessment>","recommendation":"<provider recommendation>","suggested_code":null,"requires_developer_review":true}
```

No current scan: 409; missing finding: 404; missing provider: 503; invalid/provider response: 502. A failed explanation leaves findings intact.

## Architecture — GET /api/projects/voice-ai-agent/architecture

**Schema illustration only; the current checkout has no graph adapter configured:**

```json
{"project_id":"voice-ai-agent","nodes":[{"id":"<analyzer node ID>","label":"<observed component name>","type":"controller","file":"<actual relative Java path>"}],"edges":[]}
```

Edges, when observed, have `source`, `target` (node IDs), and `relationship` (e.g. `dependency`). Missing analyzer returns HTTP 503; invalid graph returns 502. The backend never substitutes illustrative data for a service result.

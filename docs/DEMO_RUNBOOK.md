# Codely demo runbook

From the integration checkout, use Python 3.12 and Node 22. Start the backend in one terminal.

```sh
python3.12 -m venv .semgrep-local/tool-env
.semgrep-local/tool-env/bin/python -m pip install -r requirements-security.txt
export CODELY_SEMGREP_EXECUTABLE="$PWD/.semgrep-local/tool-env/bin/semgrep"
python3.12 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r requirements-integration.txt
test -f backend/.env || cp backend/.env.example backend/.env
PYTHONPATH=.:backend:m4 python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Run one backend worker so it shares its in-memory scan cache. FastAPI loads `backend/.env`. `VOICE_AI_AGENT_PATH` defaults to the sibling `VoiceAIAgentPro` checkout and accepts an absolute path. The preconfigured `python-demo` points to the bundled M3 fixture. `CODELY_PYTHON_DEMO_PATH` can point to another approved local Python directory. The bundled scanner runs bundled Python, Java, TypeScript and JavaScript rules. Keep `SEMGREP_CONFIG` empty to use them. The separate tool environment keeps the scanner’s pinned dependencies out of the API process.

Start the frontend in another terminal.

```sh
npm ci --ignore-scripts --no-audit --no-fund
test -f .env.local || cp .env.example .env.local
npm run dev
```

The browser uses `NEXT_PUBLIC_CODELY_API_URL` and Next project chat uses `CODELY_BACKEND_URL`. Both default to `http://127.0.0.1:8000`. Keep credentials in the backend environment. For a provider demonstration involving approved repository text, set `CODELY_ALLOW_EXTERNAL_AI=1`, `M4_PROVIDER=gemini`, `GEMINI_API_KEY`, and optionally `GEMINI_MODEL`. The optional Groq provider uses `GROQ_API_KEY`. Restart services after changes.

1. Open [Scanner](http://localhost:3000/scanner). Choose **VoiceAIAgentPro** and open `backend/pom.xml` in the source tree.
2. Choose **Python analysis fixture** and run the Python security scan. The trusted rules return two findings on the bundled checkout. Expand one and open its source. A repeated scan on unchanged content returns the cached results.
3. Click **Explain finding**. A configured live provider should return a structured review. An unavailable provider produces an explicit error while the findings remain in view.
4. Choose **Code Dependencies** and click **Load architecture**. The fixture shows observed Python modules. The import list includes edges only when M3 resolves them. To demo internal edges, launch with `CODELY_PYTHON_DEMO_PATH=../fixtures/structure_demo`. Its deliberately unparsable sample produces partial architecture and scanner coverage. Use the default fixture for the complete scan.
5. From VoiceAIAgentPro, use **Ask a system-design question about this repository**. Ask, “How can the architecture support 50,000 concurrent users with a limited infrastructure budget?” With a live provider configured, the answer should cite checked repository file ranges and distinguish proposed changes from observed behavior. Without credentials, show the provider-unavailable state.

If no repositories appear, check [API health](http://127.0.0.1:8000/api/health), `/api/projects`, and the configured checkout path. If scans fail, check `"$CODELY_SEMGREP_EXECUTABLE" --version` and read diagnostics. A failed scan does not mean zero findings. YAML is outside the bundled rule packs. Use the fixture for repeatable findings. For a project chat 503, check the AI opt-in and server-side key. For a 422 retrieval response, ask a question with terms present in the selected repository.

```sh
PYTHONPATH=.:backend:m4 CODELY_RUN_SEMGREP_INTEGRATION=1 python -m pytest backend/tests m4/tests -q
npm run typecheck
node --experimental-strip-types --test integrations/frontend/codely-client.test.mjs
```

## Updated graph and constraint demo

Select **Python analysis fixture** for the native Semgrep scan and explanations. Then select **Python architecture fixture**, select **Code Dependencies** and click **Load architecture**, and use module focus or **Open import** to inspect a real directed edge. The fixture reports partial coverage because it intentionally includes an unparsable Python file. Override its location with `CODELY_ARCHITECTURE_DEMO_PATH` only if needed.

Follow **Ask a system-design question about this repository**. Open **Design constraints** above the composer and enter, for example, “50,000 concurrent users, INR 15,000/month, p95 latency under 200 ms.” Standard questions retrieve matching repository code and documents. Enable **Architecture guidelines** to request M4's source-grounded review of the observed Python architecture. The API also accepts a flat constraints object and `architecture_advice: true` on `POST /api/projects/{project_id}/design-question`. Check the cited source ranges and treat proposed changes as recommendations.

Select **Python impact fixture**, run the scan, expand its finding, and select **Review static impact**. The resulting direct and transitive lists link back to source. These are statically resolved imports and indicate potential relevance only. The impact lookup requires a current completed scan from the bundled Python scanner.


Requests are limited to loopback hosts and local frontend origins by default. Set
`CODELY_ALLOWED_HOSTS` and `CODELY_ALLOWED_ORIGINS` explicitly for trusted alternatives.
The demo APIs assume a trusted local operator. The legacy CodeRAG endpoints require
`CODELY_ENABLE_LEGACY_API=1`, a strong `CODELY_LEGACY_API_TOKEN`, and a matching bearer
header. Enable them only for trusted callers and rebuild archived indexes to create
JSON metadata. The reader does not load old pickle metadata.

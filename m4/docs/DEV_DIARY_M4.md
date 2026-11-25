# M4 development diary

## Team repository integration · 2026-11-25

- Prepared `feature/ai-intelligence` from `main` at `0805457`. Main is the default branch and contains the reference archives. The frontend, FastAPI backend, and security implementation remain on separate branches. This change is additive under `m4/`. The public contribution contains only M4 code, synthetic fixtures, tests, requirements, and documentation. The original VoiceAIAgentPro materials and local credentials stayed in the workspace.
- Inspected M1 `19e9a7b`, M2 `ada47e4`, and M3 `aecdcfe` plus the extended security branch `ed8c16b`. The M4 adapter maps team `file` and array-form CWE identifiers to the existing evidence engine. Its M2 projection returns the existing `Explanation` shape. The live project-to-snapshot binding remains an M2 responsibility because the existing hook receives a finding and excerpt without a project ID.
- All 18 prior M4 tests and one new adapter regression passed. Local MiniLM and FAISS returned `semantic_status: ready` from the integrated CLI, and `pip check` passed. The M2 backend suite passed 12 tests. A separate mock-backed endpoint probe accepted an M3-shaped finding and passed M2's response validation. The frontend client suite passed four tests, and the latest M1 branch passed its TypeScript check.
- The M3 feature branch passed 75 tests with native Semgrep enabled. Extended `security-analysis` passed 209 tests with one baseline failure on Python 3.12. The expected fixture records `parser_python_version: 3.11`. The output matches that fixture when the parser version field is excluded. No teammate branch was modified to address the mismatch.
- Groq's live generation remains unverified. The most recent attempt stopped before the API call because the local Groq key was unavailable. Offline fixture results are identified as mock.

## Groq and local MiniLM integration · 2026-11-25

### Generation and intelligence

- Installed Groq SDK 1.7.0 in the M4 virtual environment. Added `GroqGenerator` for `openai/gpt-oss-120b`, strict JSON Schema structured outputs, and validation against the existing Pydantic draft contracts. `M4_PROVIDER` or the CLI override selects Groq, Gemini, or mock. The workspace now sets `M4_PROVIDER=groq`. Other callers without a provider setting retain the offline default. An explicit live provider returns its own failures.
- Groq uses the fixed HTTPS API endpoint, a bounded configurable timeout, and no automatic retry. Rate limits, timeouts, connection failures, API status errors, and invalid output produce sanitized errors. The credential is read from the environment or workspace `.env`.
- The synthetic review and architecture probes are available in `docs/demo/groq_synthetic.py`. The live command stopped at credential initialization because M4's environment lacked `GROQ_API_KEY`. There is no live result to report.

### Local embeddings and tests

- Installed Sentence Transformers 5.7.0 and downloaded the public `all-MiniLM-L6-v2` model files into the ignored virtual environment. `requirements-local.txt` installs the local encoder and FAISS together. Document and query encoding run on CPU using local files. The per-snapshot FAISS index retains structural and lexical fallback.
- An offline inference run produced finite 384-dimensional document and query vectors. The expected cross-file semantic excerpt scored 0.710 cosine in the fixture, the cross-file symbol was also retrieved, and two ready FAISS indexes using a shared encoder kept their source evidence isolated.
- The first CLI run crashed in native code on macOS when FAISS loaded before PyTorch. A scoped OpenMP thread limit during macOS encoding fixed the CLI index run. Re-tested document and query inference and project isolation with FAISS imported first. The CLI reported `semantic_status: ready`.
- Ran all 18 regressions with zero skips. The 11 existing tests passed, along with seven new tests covering strict Groq response handling, credential-safe failures, provider selection, MiniLM integration with fixture vectors, cross-file evidence, project isolation, structural fallback, and adapter output. `pip check` reported no broken dependencies.

### Team adapter

- Added `integration.review_normalized` for M2 to run in a FastAPI worker. It takes an authorized repository snapshot, a normalized M3 finding, and an injected provider, then serializes the existing response for M1. `groq` is a new value in the existing `mode` field. Team services were not available for an end-to-end integration test.

### VoiceAIAgentPro

- Re-ran the two local Semgrep rules on 70 Java targets. The scan returned one raw stack-trace finding and zero errors. The authored offline mock patch yielded one match before and zero after on a temporary copy. The original repository was only read.
- Prepared a local preview and digest check for the live payload. The user approved the finding and bounded demo excerpts. No Voice source was transmitted at this checkpoint. Live Groq interpretation and a re-scan of a live proposal are pending.

No paid billing was enabled and nothing was pushed to GitHub.

## Gemini Flash-Lite verification · 2026-11-25

The Gemini model catalog returned seven Flash-Lite IDs advertising `generateContent` with the configured workspace key. The response listed `gemini-flash-lite-latest`, `gemini-2.5-flash-lite`, `gemini-3.1-flash-lite-preview`, `gemini-3.1-flash-lite`, `gemini-3.1-flash-lite-image`, `gemini-3.5-flash-lite`, and `gemini-3.8-flash-lite-tts`. Set `GEMINI_MODEL=gemini-2.5-flash-lite` in the workspace `.env` to use the fixed text model in the same generation as the previous checkpoint. A fresh process verified the selected key and model without printing the credential. The embedding model was `gemini-embedding-001`.

| Check | Observed result |
| --- | --- |
| Local context retrieval | Found the exact affected line in synthetic `counts.py`, its enclosing function, and the related symbol in `inventory.py`. |
| Live structured defensive review | `generateContent` returned HTTP 402 for the synthetic finding about using `eval` to parse an integer. No live explanation, citation, or remediation was available to validate. |
| Live document embedding | The independent `batchEmbedContents` request returned HTTP 402. |
| Live query embedding | The independent `embedContent` request returned HTTP 402. |
| M4 regressions | All 11 passed with zero skips using `.venv/bin/python -m unittest discover -s tests -v`. Existing fixture tests covered citation validation and grounding the proposed patch in source. |

HTTP 402 persists after the model change. Its cause remains unconfirmed. Only the workspace model setting and this diary were edited. Live probes used synthetic inputs. Paid billing was not enabled and nothing was pushed to GitHub. VoiceAIAgentPro demonstration preparation remains pending until live verification succeeds.

## Gemini key rotation retest · 2026-11-25

Verified that a fresh M4 provider process selected the credential from the workspace `gen ai hack/.env` after clearing inherited credential variables. The credential was never printed. The initial run in the network-restricted sandbox could not connect. The network-enabled rerun recorded the following results through the existing Gemini provider.

| Live probe | Observed result |
| --- | --- |
| Generation model metadata | Passed for `gemini-2.5-flash`, which advertises `generateContent`. |
| Embedding model metadata | Passed for `gemini-embedding-001`, which advertises `embedContent`. |
| Structured generation with a synthetic JSON prompt | HTTP 402 from `generateContent`. |
| Document embedding with synthetic text | HTTP 402 from `batchEmbedContents`. |
| Query embedding with synthetic text | HTTP 402 from `embedContent`. |

HTTP 402 persists on all three live operations. Model metadata is reachable with the replacement key. The generation and embedding requests returned no usable output. The exact cause of HTTP 402 was not confirmed.

All 11 M4 regression tests passed with zero skips using `.venv/bin/python -m unittest discover -s tests -v`. The diary was the only file edited. Paid billing was not enabled, nothing was pushed to GitHub, and the VoiceAIAgentPro demonstration was not run. The live probes sent synthetic data only.

## Live verification follow-up · 2026-11-25

This follow-up supersedes earlier statements in this diary that no Gemini credential was configured or live verification had not begun.

- **Configuration/security:** Added `python-dotenv` and load `.env` during Gemini provider initialization. A fresh process initialized the provider from the workspace `.env`; its values were not printed. Restricted the `.env` file to owner read/write and added ignore rules beside the workspace `.env` and inside M4, plus local ignores for virtualenvs and bytecode. Provider errors continue to expose status codes only, not request credentials or provider response bodies; a regression test covers this. The Codely M4 folder is not itself a Git repository, and the `.env` is in its parent workspace; no commit or push was performed.
- **Model availability:** Live metadata requests succeeded for `models/gemini-2.5-flash` and `models/gemini-embedding-001`. `check-gemini` checks both configured models without uploading source.
- **Live generation/embedding:** Requests used only a temporary synthetic Python example and synthetic text. Both structured `generateContent` and document embeddings returned HTTP 402. No actual Gemini review or embedding vector was produced; this is an upstream access/quota blocker, not a successful live generation test.
- **Synthetic offline check:** A three-file dataset produced a ready in-memory FAISS index using deterministic fixture vectors; the matching unsafe-evaluation snippet ranked first (cosine similarity 1.0). The offline review was labeled `mode: mock` and included impact/remediation fields. This is not a Gemini result.
- **Tests/dependencies:** Added `python-dotenv`; installed required, parser, and FAISS dependencies into the module-local `.venv`. All 11 M4 unit tests pass, including dotenv/model-check and credential-error coverage. Python compilation also succeeds.
- **Live/mock comparison:** No live generation fields were returned because of HTTP 402, so a content comparison against the mock is not possible yet. The synthetic offline run confirms the mock contract and `mode: mock`; it is not substituted for Gemini output.
- **VoiceAIAgentPro:** No source was transmitted. Its existing walkthrough outputs are authored mock results plus local static-scan results. A live comparison on the Voice source is blocked pending explicit user permission and successful live generation access.
- **FastAPI handoff:** Added a threadpool-based worker boundary and request/error/logging guidance to `docs/INTEGRATION.md`. M2's service and routes were not modified.

## Phase 1 · Audit and roadmap

Status: audited the supplied sources and selected an isolated Python module in the workspace. No team application, M2 interface, or M3 implementation was supplied.

- CodeRAG backend: inspected `indexer.py`, `retriever.py`, `models/embedding_service.py`, and the archived index inventory. Reused the conceptual chunk → embed → FAISS lookup → source metadata pipeline. Its fixed line chunks, document-only embedding mode, and pickle metadata motivated new implementations. No archived index or pickle was loaded.
- VS Code extension: inspected `src/localIndex.ts` for overlap and import matching ideas. The extension is reference material.
- VoiceAIAgentPro: inventoried Spring Boot and React/TypeScript inputs and inspected source declarations for the seven requested classes. The private demo guide stayed in the local workspace.
- Initial checks: Python 3.12 available. Default pip installation failed because the package host was unreachable in the sandbox. Bundled Python includes Pydantic and NumPy. No Gemini credential or Semgrep executable was detected.

### Implementation order

1. Define scanner, source, and response contracts. Add Gemini JSON and offline provider boundaries.
2. Build source snapshots, structural/lexical context, and per-snapshot FAISS search.
3. Validate source evidence and generate proposed diffs. Expose M2/M3 integration points and fixture-based tests.
4. Add graph-based architecture advice after security tests pass.
5. Evaluate with the real repository locally and document verification gaps.

Suggested commit: `docs: record M4 source audit and delivery roadmap`

## Phases 2–4 · Provider, repository context, and FAISS

Status: implemented and tested through Pydantic, mocked Gemini transport, native parser and FAISS fixture tests. Live Gemini awaits a configured key.

- Files: `contracts.py`, `gemini.py`, `context.py`, and the requirements files.
- Decisions: REST with explicit model settings, validated JSON, timeouts, and sanitized provider errors. Python AST and optional Tree-sitter yield source spans. Bounded line chunks cover unparsed text. Exact evidence precedes structural and lexical/semantic candidates.
- Reuse: CodeRAG's embedding/FAISS flow and source metadata pattern. New: filtered snapshots, separate retrieval modes, cosine scores, per-project instances, and fallback without deserializing saved data.
- Tests: structured JSON and task modes, parser spans, exact-line priority, cross-file links, redaction, path validation, project isolation and real FAISS with fixture vectors. The first six tests passed during the review milestone. After network permission, optional dependencies installed in the workspace. Final suite passed nine tests with zero skips.
- Integration: M2 supplies a private immutable checkout and owns project lifetime and source-access policy.

Suggested commit: `feat: add Gemini provider and repository context retrieval`

## Phases 5–6 · Defensive review and remediation

Status: implemented and tested offline, including patch application and re-scan on VoiceAIAgentPro. Real Gemini interpretation is pending.

- Files: `review.py`, `__main__.py`, `tests/test_m4.py`.
- Decisions: preserve scanner findings with their severity and ID. Validate citation IDs against excerpts. Construct original lines and diff from the snapshot. Reject overlapping edits and edits against redacted files.
- New contribution: M3 finding contract, demo JSON adapter, source validation, and secure-edit artifacts. The local adapter's deterministic ID is location-based.
- Tests: ran fixture review, malformed citations, JSON contract handling, exact-source diff, and the isolated real-file rescan documented below.
- Integration: M3 supplies normalized findings. M2 or the M3 worker stages approved proposals and owns the full-ruleset verification.

Suggested commit: `feat: explain scanner findings with source evidence and proposed diffs`

## Phase 7 · Architecture guidance

Status: implemented and tested with an observed graph fixture and an authored mock proposal.

- Files: `architecture.py`, `tests/test_m4.py`, integration examples.
- Decisions: require source anchors on observed graph entries, preserve the input graph, and validate proposed node/edge IDs and citation references.
- New contribution: source-linked recommendations and graph proposal contract. The architecture test rejected an unknown endpoint and preserved the observed graph on valid input.
- Integration: M3 supplies the authoritative graph. M2 supplies a selected subgraph. The frontend assigns positions.

Suggested commit: `feat: add source-linked architecture recommendations`

## Phases 8–9 · Real repository evaluation and team handoff

Status: local demo and handoff complete. Team integration is pending.

- Files: `README.md`, `docs/INTEGRATION.md`, `docs/VOICE_DEMO.md`, `docs/demo/`.
- Actual result: 261 indexed source files and 1,964 chunks. Semgrep ran two Java rules on 70 targets, yielding one finding and zero errors. The mock review cited an additional file. A local static re-scan of the edited copy returned zero matches for the original rule. The original repository was read locally and its application and provider integrations were not run.
- Problems resolved: Semgrep initially attempted to create a settings directory outside the workspace. Redirected its state into the workspace and repeated the scan with metrics and version checks disabled.
- New contribution: demo rules and authored review fixture, an isolated rescan, source-checked architecture fixture, and reproducible commands. No shared team code or branch was modified.

Suggested commit: `docs: deliver M4 integration and VoiceAIAgentPro verification demo`

## Remaining checklist

- [ ] Verify live Gemini generation and embeddings with an approved source set and a configured credential.
- [ ] Wire the M2 backend and M3 normalized findings, structural graph, and full ruleset.
- [ ] Validate proposed changes with the team ruleset and application tests in a team-controlled isolation workflow.
- [ ] Evaluate retrieval recall on larger repositories, stronger secret detection, and project index lifecycle.
- [ ] Integrate Git change intelligence and CI/CD if the team chooses those stretch goals.
- [ ] Create or use `feature/ai-intelligence` when Git integration is explicitly approved.

## Delivery inventory

All module files were created in the isolated workspace. No source from the attachments was edited.

| Area | Files |
| --- | --- |
| Module | `ai_intelligence/__init__.py`, `__main__.py`, `contracts.py`, `gemini.py`, `context.py`, `review.py`, `architecture.py` |
| Dependencies | `requirements.txt`, `requirements-parsers.txt`, `requirements-semantic.txt` |
| Tests | `tests/test_m4.py` |
| Handoff | `README.md`, `docs/INTEGRATION.md`, `docs/DEV_DIARY_M4.md`, `docs/VOICE_DEMO.md` |
| Demo | `docs/demo/semgrep.yml`, `walkthrough.py`, `voice-demo-results.json` |
| Mentor deck | `Codely-M4-Mentor.pptx`, delivered alongside the module |

The four slides cover individual ownership, source evidence, the real-rule rescan, and team integration. The deck package passed structural checks and all slides were rendered for layout review.

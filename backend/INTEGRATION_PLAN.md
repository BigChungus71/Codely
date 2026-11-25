# Inspection and integration plan

The supplied CodeRAG foundation arrived as `coderag-backend-main.zip` with no Git history. It was extracted into its own repository; `feature/backend-core` contains a baseline snapshot and the implementation. The original archives remain unchanged. There is no configured remote, so no hosted PR is created.

FastAPI entry: `main.py`. Existing routes: `/`, `/health`, `/index`, `/query`, `/embed`, `/retrieve`, `/retrieve-detailed`, `/validate`, `/upload-doc`, `/documents`, `/documents/{doc_id}`, `/memory`, `/memory/clear`, `/blast-radius`, `/debug-error`, `/review-code`, `/lint`. `/upload-doc` indexes documents, not ZIP repositories; it is preserved without expanding upload scope.

`indexer.py` chunks source and embeds it into FAISS plus pickle metadata. `retriever.py` retrieves nearest chunks. `models/embedding_service.py` and `main.call_llm` use Gemini; `architect_service.py` provides prose AI reports, not a structural graph. `memory_store.py` and `doc_processor.py` manage document RAG. Existing Pydantic schemas are in `models/`. Full dependencies include FAISS/numpy, Gemini SDK, PDF and multipart handling, FastAPI and Uvicorn. No scanner or structural graph service was present.

VoiceAIAgentPro root is the sibling `../../VoiceAIAgentPro`. Maven Java 17 / Spring Boot 3.2.4 backend: `backend/src/main/java/com/voiceai/contact`; test sources: `backend/src/test/java`; React/TypeScript/Vite frontend: `frontend/src`, build manifest `frontend/package.json`. Documentation: root/backend READMEs and `docs/`, including architecture gates and provider/audio contracts. Representative source areas include `domain/agent`, `domain/realtime`, `domain/voice`, `domain/provider`, and frontend `features/agent` and `features/realtime`.

Implementation order: preserve legacy routes with lazy optional imports; add read-only configured project access; expose validated scanner/explanation/graph adapters; hash-bind completed scan cache; smoke-test browser flow and truthful unavailable states; publish startup and teammate contracts. No large refactor, target edits, duplicated analysis engines, generalized upload platform, or production infrastructure.

GitHub integration: this copy is packaged under backend/ in BigChungus71/Codely, on feature/backend-core based on the remote main history. See ../BACKEND_INTEGRATION.md for the separate frontend history and compatibility report. The extracted CodeRAG source repository is preserved separately.

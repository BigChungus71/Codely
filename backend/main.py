import hmac
import os
import time
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from models.schemas import (
    IndexRequest, IndexResponse,
    QueryRequest, QueryResponse,
    LintRequest, RetrieveResponse,
    EmbeddingRequest, EmbeddingResponse,
    RetrieveDetailedResponse, ChunkDetail,
    ValidateRequest, ConfidenceResponse,
    DocUploadResponse,
)
from models.architect_schemas import ArchitectRequest, ArchitectResponse
# ── Load env & configure LLM ────────────────────────────────────────────────
load_dotenv()

# Google Gemini for LLM
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")

print(f"[CodeRAG Backend] Starting with model: {GEMINI_MODEL}")


# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="CodeRAG API",
    description="Vector Intelligence Layer for CodeRAG — Semantic Code Retrieval & AI-Grounded Generation",
    version="3.0.0",
)



def environment_list(name, default):
    return [part.strip() for part in os.getenv(name, default).split(',') if part.strip()]


allowed_origins = environment_list(
    'CODELY_ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000',
)
public_paths = {'/', '/health', '/docs', '/redoc', '/openapi.json', '/docs/oauth2-redirect'}


@app.middleware('http')
async def screen_requests(request: Request, call_next):
    origin = request.headers.get('origin')
    if origin and origin not in allowed_origins:
        return JSONResponse({'detail': 'Origin is not allowed'}, status_code=403)
    path = request.url.path.rstrip('/') or '/'
    if not path.startswith('/api/') and path not in public_paths:
        if os.getenv('CODELY_ENABLE_LEGACY_API') != '1':
            return JSONResponse({'detail': 'Legacy API disabled'}, status_code=404)
        token = os.getenv('CODELY_LEGACY_API_TOKEN', '')
        supplied = request.headers.get('authorization', '')
        if not token or not hmac.compare_digest(supplied.encode(), f'Bearer {token}'.encode()):
            return JSONResponse({'detail': 'Legacy API authorization required'}, status_code=401)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware, allow_origins=allowed_origins, allow_methods=['GET', 'POST', 'DELETE'],
    allow_headers=['Content-Type', 'Authorization'],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=environment_list(
    'CODELY_ALLOWED_HOSTS', 'localhost,127.0.0.1,[::1]',
))


# ── LLM: Google Gemini ──────────────────────────────────────────────────────
def call_llm(prompt: str) -> str:
    """
    Calls Google Gemini API for query refinement and code generation.
    Used by the /query endpoint for RAG-grounded answers.
    """
    if not GEMINI_API_KEY:
        return "LLM service unavailable (GEMINI_API_KEY not set). Grounded context is still available via /retrieve."

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"[CodeRAG LLM] Gemini Error: {str(e)}")
        return f"I encountered an error while processing the LLM request. However, I have retrieved the relevant code context for your query."


# ══════════════════════════════════════════════════════════════════════════════
#  CORE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {
        "status": "CodeRAG backend running",
        "version": "3.0.0",
        "engine": "CodeRAG Semantic Engine",
        "features": [
            "Smart Context Retrieval",
            "Hallucination & Confidence Checker",
            "Project Memory & Doc Upload RAG",
            "Architect Studio (Blast Radius, Debug, Review)"
        ]
    }


@app.post("/index", response_model=IndexResponse)
def index_endpoint(req: IndexRequest):
    """
    Walk the repo at req.repo_path, embed all source files,
    and save the FAISS index to req.index_path.
    """
    from indexer import index_repo
    if not os.path.isdir(req.repo_path):
        raise HTTPException(status_code=400, detail=f"Path not found: {req.repo_path}")
    try:
        total = index_repo(req.repo_path, req.index_path)
        return IndexResponse(status="indexed", chunks_indexed=total)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query", response_model=QueryResponse)
def query_endpoint(req: QueryRequest):
    """
    High-level RAG: Retrieve → (Optional Doc Search) → Refine → Answer → Validate.
    """
    from retriever import retrieve, format_context
    from validator import check_hallucinations, check_hallucinations_detailed, lint_code
    from models.embedding_service import embedding_service
    from memory_store import document_store, query_memory
    faiss_path = req.index_path + ".faiss"
    if not os.path.exists(faiss_path):
        raise HTTPException(
            status_code=400,
            detail="Index not found. Call POST /index first."
        )

    # 1. Retrieve relevant code chunks
    chunks = retrieve(req.query, req.index_path, top_k=8)
    context = format_context(chunks)

    # 2. Optionally search uploaded docs
    doc_context = ""
    has_doc_results = False
    if req.include_docs and document_store.documents:
        q_emb = embedding_service.encode([req.query])[0]
        doc_results = document_store.search(q_emb, top_k=3)
        if doc_results:
            has_doc_results = True
            doc_parts = [f"// Source: {r['source']}\n{r['text']}" for r in doc_results]
            doc_context = "\n\n---\n\n".join(doc_parts)

    # 3. Build grounded prompt
    full_context = context
    if doc_context:
        full_context += f"\n\n=== UPLOADED DOCUMENTATION ===\n{doc_context}"

    prompt = f"""You are CodeRAG, an expert coding assistant.
Answer the question using ONLY the repository code and documentation provided below.
If the answer is not in the provided context, say: "I couldn't find this in the retrieved context."

=== RETRIEVED REPOSITORY CODE ===
{full_context}

=== ACTIVE FILE ===
{req.active_file or "(none)"}

=== QUESTION ===
{req.query}
"""

    # 4. Call LLM
    answer = call_llm(prompt)

    # 5. Validate — structured confidence check
    confidence = check_hallucinations_detailed(answer, chunks)
    warnings = check_hallucinations(answer, chunks)

    # 6. Deduplicate source file paths
    sources = list(dict.fromkeys(c["file"] for c in chunks))

    # 7. Record in project memory
    query_memory.add_query(
        query=req.query,
        sources=sources,
        chunk_count=len(chunks),
        confidence=confidence["overall_confidence"],
        has_doc_results=has_doc_results
    )

    return QueryResponse(
        answer=answer,
        sources=sources,
        warnings=warnings,
        confidence=confidence
    )


@app.post("/embed", response_model=EmbeddingResponse)
def embed_endpoint(req: EmbeddingRequest):
    """
    Stateless endpoint to get embeddings from configured provider (Azure/OpenAI).
    Used by VS Code extension for local indexing and retrieval.
    """
    from models.embedding_service import embedding_service
    try:
        if req.input_type == "passage":
            embeddings = embedding_service.encode_passage(req.texts)
        else:
            embeddings = embedding_service.encode(req.texts)
        return EmbeddingResponse(embeddings=embeddings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve_endpoint(req: QueryRequest):
    """
    Pure RAG: Only retrieves the context chunks for downstream LLMs (like VS Code Copilot).
    """
    from retriever import retrieve, format_context
    faiss_path = req.index_path + ".faiss"
    if not os.path.exists(faiss_path):
        raise HTTPException(status_code=400, detail="Index not found.")

    chunks = retrieve(req.query, req.index_path, top_k=10)
    context = format_context(chunks)
    sources = list(dict.fromkeys(c["file"] for c in chunks))

    print(f"\n[CodeRAG] 🔍 Context requested for: '{req.query}'")
    print(f"[CodeRAG] 📦 Retrieved {len(chunks)} chunks from: {sources}\n")

    return RetrieveResponse(context=context, sources=sources)


# ══════════════════════════════════════════════════════════════════════════════
#  FEATURE: Smart Context Visualizer
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/retrieve-detailed", response_model=RetrieveDetailedResponse)
def retrieve_detailed_endpoint(req: QueryRequest):
    """
    Detailed retrieval with per-chunk scores, files, and line ranges.
    Powers the Smart Context Visualizer in the VS Code webview.
    """
    from retriever import retrieve, format_context
    from models.embedding_service import embedding_service
    from memory_store import document_store, query_memory
    faiss_path = req.index_path + ".faiss"
    if not os.path.exists(faiss_path):
        raise HTTPException(status_code=400, detail="Index not found.")

    start_time = time.time()
    chunks = retrieve(req.query, req.index_path, top_k=10)

    # Also search uploaded docs if requested
    doc_chunks = []
    if req.include_docs and document_store.documents:
        q_emb = embedding_service.encode([req.query])[0]
        doc_results = document_store.search(q_emb, top_k=3)
        for dr in doc_results:
            doc_chunks.append(ChunkDetail(
                file=dr["source"],
                start_line=0,
                text=dr["text"][:500],  # Truncate for UI
                score=dr["score"],
                source_type="document"
            ))

    elapsed_ms = round((time.time() - start_time) * 1000, 2)

    detailed_chunks = []
    for c in chunks:
        detailed_chunks.append(ChunkDetail(
            file=c["file"],
            start_line=c.get("start_line", 0),
            text=c["text"][:500],  # Truncate for UI display
            score=c.get("score", 0.0),
            source_type="code"
        ))

    # Merge doc chunks
    detailed_chunks.extend(doc_chunks)

    sources = list(dict.fromkeys(c.file for c in detailed_chunks))

    return RetrieveDetailedResponse(
        chunks=detailed_chunks,
        total_chunks=len(detailed_chunks),
        sources=sources,
        query=req.query,
        retrieval_time_ms=elapsed_ms
    )


# ══════════════════════════════════════════════════════════════════════════════
#  FEATURE: Hallucination & Confidence Checker
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/validate", response_model=ConfidenceResponse)
def validate_endpoint(req: ValidateRequest):
    """
    Validate generated code against retrieved context.
    Returns structured confidence report with verified/warning/error symbols.
    """
    from validator import check_hallucinations, check_hallucinations_detailed, lint_code
    report = check_hallucinations_detailed(req.code, req.context_chunks)
    return ConfidenceResponse(**report)


# ══════════════════════════════════════════════════════════════════════════════
#  FEATURE: Project Memory + Doc Upload RAG
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/upload-doc", response_model=DocUploadResponse)
async def upload_doc_endpoint(file: UploadFile = File(...)):
    """
    Upload a document (PDF, MD, TXT, etc.) to be indexed for hybrid RAG.
    The document is chunked, embedded, and stored in-memory.
    """
    from memory_store import document_store, query_memory
    from doc_processor import extract_text, chunk_document
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file.")

    if len(file_bytes) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="File too large (max 10MB).")

    try:
        text = extract_text(file_bytes, file.filename)
        chunks = chunk_document(text, file.filename)

        if not chunks:
            raise HTTPException(status_code=400, detail="No extractable text found in file.")

        result = document_store.add_document(file.filename, chunks)
        print(f"[CodeRAG] 📄 Document uploaded: {file.filename} ({len(chunks)} chunks)")

        return DocUploadResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process document: {str(e)}")


@app.get("/documents")
def list_documents():
    """List all uploaded documents."""
    from memory_store import document_store, query_memory
    return {"documents": document_store.list_documents()}


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    """Remove an uploaded document."""
    from memory_store import document_store, query_memory
    if document_store.remove_document(doc_id):
        return {"status": "deleted", "doc_id": doc_id}
    raise HTTPException(status_code=404, detail="Document not found.")


@app.get("/memory")
def get_memory(limit: int = 20):
    """Get project query history (recent queries, sources, confidence)."""
    from memory_store import document_store, query_memory
    return {"history": query_memory.get_history(limit)}


@app.post("/memory/clear")
def clear_memory():
    """Clear all project memory."""
    from memory_store import document_store, query_memory
    query_memory.clear()
    document_store.clear()
    return {"status": "cleared"}


# ══════════════════════════════════════════════════════════════════════════════
#  FEATURE: Architect Studio (Blast Radius, Debug, Review)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/blast-radius", response_model=ArchitectResponse)
def blast_radius_endpoint(req: ArchitectRequest):
    """Predict the semantic blast radius of changing a specific piece of code."""
    from architect_service import ArchitectService
    architect_service = ArchitectService()
    report = architect_service.generate_report(req.input_text, "blast_radius", req.context_chunks)
    return ArchitectResponse(report_markdown=report, confidence_score=0.9, affected_files=[])

@app.post("/debug-error", response_model=ArchitectResponse)
def debug_error_endpoint(req: ArchitectRequest):
    """Automatically diagnose error logs based on codebase context."""
    from architect_service import ArchitectService
    architect_service = ArchitectService()
    report = architect_service.generate_report(req.input_text, "debug", req.context_chunks)
    return ArchitectResponse(report_markdown=report, confidence_score=0.9, affected_files=[])

@app.post("/review-code", response_model=ArchitectResponse)
def review_code_endpoint(req: ArchitectRequest):
    """Review a file against repository-wide conventions."""
    from architect_service import ArchitectService
    architect_service = ArchitectService()
    report = architect_service.generate_report(req.input_text, "review", req.context_chunks)
    return ArchitectResponse(report_markdown=report, confidence_score=0.9, affected_files=[])


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITY ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/lint")
def lint_endpoint(req: LintRequest):
    """Run static analysis on a code snippet."""
    from validator import check_hallucinations, check_hallucinations_detailed, lint_code
    output = lint_code(req.code, req.lang)
    return {"output": output}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "engine": "CodeRAG Semantic Engine",
        "llm": GEMINI_MODEL,
        "version": "3.0.0",
        "features": {
            "context_visualizer": True,
            "confidence_checker": True,
            "doc_upload_rag": True,
            "project_memory": True,
            "architect_studio": True
        }
    }



# Demo APIs require no vector store or AI credentials at startup.
from codely.api import router as codely_router
app.include_router(codely_router)


@app.exception_handler(ModuleNotFoundError)
async def optional_dependency_unavailable(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=503, content={"detail": "Optional CodeRAG dependency unavailable; install requirements.txt for legacy analysis routes"})


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="127.0.0.1", port=port)

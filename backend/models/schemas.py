from pydantic import BaseModel
from typing import Optional


# ── Embedding ────────────────────────────────────────────────────────────────
class EmbeddingRequest(BaseModel):
    texts: list[str]
    input_type: str = "query"

class EmbeddingResponse(BaseModel):
    embeddings: list[list[float]]


# ── Indexing ─────────────────────────────────────────────────────────────────
class IndexRequest(BaseModel):
    repo_path: str
    index_path: str = "data/coderag.index"

class IndexResponse(BaseModel):
    status: str
    chunks_indexed: int


# ── Query & Retrieval ────────────────────────────────────────────────────────
class QueryRequest(BaseModel):
    query: str
    active_file: Optional[str] = ""
    cursor_context: Optional[str] = ""
    index_path: str = "data/coderag.index"
    include_docs: bool = False  # Whether to also search uploaded docs

class QueryResponse(BaseModel):
    answer: str
    sources: list[str]
    warnings: list[str]
    confidence: Optional[dict] = None  # Structured confidence data


# ── Detailed Retrieval (for Context Visualizer) ─────────────────────────────
class ChunkDetail(BaseModel):
    file: str
    start_line: int
    text: str
    score: float
    source_type: str = "code"  # "code" or "document"

class RetrieveResponse(BaseModel):
    context: str
    sources: list[str]

class RetrieveDetailedResponse(BaseModel):
    chunks: list[ChunkDetail]
    total_chunks: int
    sources: list[str]
    query: str
    retrieval_time_ms: float


# ── Confidence / Validation ─────────────────────────────────────────────────
class ValidateRequest(BaseModel):
    code: str
    context_chunks: list[dict]

class SymbolCheck(BaseModel):
    symbol: str
    type: str
    reason: Optional[str] = None

class ConfidenceResponse(BaseModel):
    overall_confidence: float
    level: str  # "high" | "medium" | "low"
    verified: list[SymbolCheck]
    warnings: list[SymbolCheck]
    errors: list[SymbolCheck]
    stats: dict


# ── Lint ─────────────────────────────────────────────────────────────────────
class LintRequest(BaseModel):
    code: str
    lang: str = "python"


# ── Doc Upload ───────────────────────────────────────────────────────────────
class DocUploadResponse(BaseModel):
    doc_id: str
    name: str
    chunk_count: int
    status: str

class DocListItem(BaseModel):
    doc_id: str
    name: str
    chunk_count: int
    uploaded_at: float


# ── Memory ───────────────────────────────────────────────────────────────────
class MemoryEntry(BaseModel):
    query: str
    sources: list[str]
    chunk_count: int
    confidence: Optional[float] = None
    has_doc_results: bool = False
    timestamp: float

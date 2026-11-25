"""
CodeRAG Memory Store
====================
In-memory store for project memory (query history) and uploaded document storage.
Provides the data layer for the Project Memory + Doc Upload RAG feature.
"""

import time
import numpy as np
from typing import Optional
from models.embedding_service import embedding_service


class DocumentStore:
    """Stores uploaded documents and their embeddings for hybrid RAG retrieval."""

    def __init__(self):
        self.documents: list[dict] = []  # {doc_id, name, chunks: [{text, embedding}]}
        self._doc_counter = 0

    def add_document(self, name: str, chunks: list[str]) -> dict:
        """Embed and store document chunks. Returns doc metadata."""
        self._doc_counter += 1
        doc_id = f"doc_{self._doc_counter}"

        # Generate embeddings for all chunks
        embeddings = embedding_service.encode_passage(chunks)

        doc_chunks = []
        for text, emb in zip(chunks, embeddings):
            doc_chunks.append({
                "text": text,
                "embedding": emb
            })

        doc_entry = {
            "doc_id": doc_id,
            "name": name,
            "chunk_count": len(chunks),
            "uploaded_at": time.time(),
            "chunks": doc_chunks
        }

        self.documents.append(doc_entry)
        return {
            "doc_id": doc_id,
            "name": name,
            "chunk_count": len(chunks),
            "status": "indexed"
        }

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        """Search all uploaded documents using cosine similarity."""
        if not self.documents:
            return []

        q_vec = np.array(query_embedding, dtype="float32")
        q_norm = np.linalg.norm(q_vec)
        if q_norm == 0:
            return []
        q_vec = q_vec / q_norm

        results = []
        for doc in self.documents:
            for chunk in doc["chunks"]:
                c_vec = np.array(chunk["embedding"], dtype="float32")
                c_norm = np.linalg.norm(c_vec)
                if c_norm == 0:
                    continue
                c_vec = c_vec / c_norm
                score = float(np.dot(q_vec, c_vec))
                results.append({
                    "text": chunk["text"],
                    "source": f"[DOC] {doc['name']}",
                    "doc_id": doc["doc_id"],
                    "score": score
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def list_documents(self) -> list[dict]:
        """Return metadata for all uploaded documents."""
        return [
            {
                "doc_id": d["doc_id"],
                "name": d["name"],
                "chunk_count": d["chunk_count"],
                "uploaded_at": d["uploaded_at"]
            }
            for d in self.documents
        ]

    def remove_document(self, doc_id: str) -> bool:
        """Remove a document by ID."""
        for i, doc in enumerate(self.documents):
            if doc["doc_id"] == doc_id:
                self.documents.pop(i)
                return True
        return False

    def clear(self):
        """Remove all uploaded documents."""
        self.documents.clear()
        self._doc_counter = 0


class QueryMemory:
    """Stores query history for project memory feature."""

    def __init__(self, max_entries: int = 50):
        self.history: list[dict] = []
        self.max_entries = max_entries

    def add_query(self, query: str, sources: list[str], 
                  chunk_count: int, confidence: Optional[float] = None,
                  has_doc_results: bool = False):
        """Record a query and its retrieval metadata."""
        entry = {
            "query": query,
            "sources": sources,
            "chunk_count": chunk_count,
            "confidence": confidence,
            "has_doc_results": has_doc_results,
            "timestamp": time.time()
        }
        self.history.append(entry)
        # Trim old entries
        if len(self.history) > self.max_entries:
            self.history = self.history[-self.max_entries:]

    def get_history(self, limit: int = 20) -> list[dict]:
        """Return recent query history, newest first."""
        return list(reversed(self.history[-limit:]))

    def clear(self):
        """Clear all query history."""
        self.history.clear()


# ── Singleton Instances ──────────────────────────────────────────────────────
document_store = DocumentStore()
query_memory = QueryMemory()

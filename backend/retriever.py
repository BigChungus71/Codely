import pickle
import numpy as np
import faiss
from indexer import embedding_service  # reuse the same instance if imported there


def retrieve(
    query: str,
    index_path: str = "data/coderag.index",
    top_k: int = 8
) -> list[dict]:
    """
    Embed query, search FAISS index, return top_k most relevant chunks.
    Each chunk is a dict: { file, start_line, text }
    """
    # Load index and metadata
    index = faiss.read_index(index_path + ".faiss")
    with open(index_path + ".pkl", "rb") as f:
        chunks = pickle.load(f)

    # Embed and normalize query
    q_embed = np.array(embedding_service.encode([query])).astype("float32")
    faiss.normalize_L2(q_embed)

    # Search
    k = min(top_k, len(chunks))
    scores, ids = index.search(q_embed, k)

    results = []
    for score, idx in zip(scores[0], ids[0]):
        if idx < 0 or idx >= len(chunks):
            continue
        chunk = chunks[idx].copy()
        chunk["score"] = float(score)
        results.append(chunk)

    return results


def format_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into a clean context block for the LLM prompt."""
    parts = []
    for c in chunks:
        header = f"// File: {c['file']}  (line {c['start_line']})"
        parts.append(f"{header}\n{c['text']}")
    return "\n\n---\n\n".join(parts)

import os
import json
import numpy as np
import faiss
from models.embedding_service import embedding_service


SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".java", ".go",
    ".cpp", ".c", ".cs", ".rb", ".php", ".rs"
}

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__",
    "dist", "build", ".venv", "venv", ".idea"
}


def chunk_file(filepath: str, content: str, chunk_size: int = 40) -> list[dict]:
    """Split file into overlapping chunks of chunk_size lines."""
    lines = content.splitlines()
    chunks = []
    step = chunk_size // 2  # 50% overlap for better retrieval

    for i in range(0, len(lines), step):
        chunk_lines = lines[i : i + chunk_size]
        text = "\n".join(chunk_lines).strip()
        if len(text) < 30:  # skip near-empty chunks
            continue
        chunks.append({
            "file": filepath,
            "start_line": i,
            "text": text
        })
    return chunks


def index_repo(repo_path: str, index_path: str = "data/coderag.index") -> int:
    """
    Walk repo_path, chunk all supported files, embed them,
    and save FAISS index + metadata to index_path.
    Returns number of chunks indexed.
    """
    all_chunks = []

    for root, dirs, files in os.walk(repo_path):
        # Prune skip dirs in-place so os.walk doesn't recurse into them
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            filepath = os.path.join(root, filename)
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                chunks = chunk_file(filepath, content)
                all_chunks.extend(chunks)
            except Exception as e:
                print(f"[CodeRAG Indexer] Skipping {filepath}: {e}")

    if not all_chunks:
        raise ValueError(f"No supported source files found in {repo_path}")

    print(f"[CodeRAG Indexer] Embedding {len(all_chunks)} chunks...")
    texts = [c["text"] for c in all_chunks]
    embeddings = embedding_service.encode_passage(texts)
    embeddings = np.array(embeddings).astype("float32")

    # Normalize for cosine similarity via inner product
    faiss.normalize_L2(embeddings)
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)

    # Save index and metadata
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    faiss.write_index(index, index_path + ".faiss")
    with open(index_path + ".json", "w", encoding="utf-8") as f:
        json.dump(all_chunks, f)

    print(f"[CodeRAG Indexer] Done. {len(all_chunks)} chunks saved to {index_path}")
    return len(all_chunks)

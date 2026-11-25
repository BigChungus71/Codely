"""
CodeRAG Document Processor
===========================
Handles extraction and chunking of uploaded documents (PDF, Markdown, Plain Text)
for the Doc Upload RAG feature.
"""

import io
from typing import Optional


def extract_pdf_text(file_bytes: bytes) -> str:
    """Extract text content from a PDF file."""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        return "\n\n".join(pages)
    except Exception as e:
        raise ValueError(f"Failed to parse PDF: {str(e)}") from e


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Extract text based on file extension."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        return extract_pdf_text(file_bytes)
    elif ext in ("md", "txt", "rst", "log", "csv", "json", "yaml", "yml", "toml", "ini", "cfg"):
        return file_bytes.decode("utf-8", errors="ignore")
    elif ext in ("py", "js", "ts", "java", "go", "cpp", "c", "cs", "rb", "php", "rs"):
        return file_bytes.decode("utf-8", errors="ignore")
    else:
        # Try UTF-8 decoding as fallback
        try:
            return file_bytes.decode("utf-8", errors="ignore")
        except Exception:
            raise ValueError(f"Unsupported file type: .{ext}")


def chunk_document(text: str, source_name: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """
    Chunk document text into overlapping segments for embedding.
    Uses character-based chunking (better for prose/docs vs line-based for code).
    """
    if not text or not text.strip():
        return []

    chunks = []
    text = text.strip()

    # For short documents, return as single chunk
    if len(text) <= chunk_size:
        return [text]

    start = 0
    while start < len(text):
        end = start + chunk_size

        # Try to break at paragraph or sentence boundary
        if end < len(text):
            # Look for paragraph break
            para_break = text.rfind("\n\n", start, end)
            if para_break > start + chunk_size // 2:
                end = para_break + 2
            else:
                # Look for sentence break
                for sep in [". ", ".\n", "! ", "? "]:
                    sent_break = text.rfind(sep, start, end)
                    if sent_break > start + chunk_size // 2:
                        end = sent_break + len(sep)
                        break

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(chunk_text)

        # Move start with overlap
        start = end - overlap if end < len(text) else len(text)

    return chunks

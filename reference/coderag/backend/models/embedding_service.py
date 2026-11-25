import os
from dotenv import load_dotenv
from fastapi import HTTPException
import google.generativeai as genai

load_dotenv()

class EmbeddingService:
    def __init__(self):
        # ── Configuration Detection ───────────────────────────────────────────
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.model = "models/gemini-embedding-001"

        if self.gemini_key:
            print(f"[EmbeddingService] Using Google Gemini Embedding Model: {self.model}")
            genai.configure(api_key=self.gemini_key)
            self.client = True
        else:
            print("[EmbeddingService] CRITICAL: No GEMINI_API_KEY found.")
            self.client = None

    def encode(self, texts: list[str], **kwargs) -> list[list[float]]:
        """
        Embed a list of strings using Google Gemini.
        """
        if not texts:
            return []
        
        if not self.client:
            raise HTTPException(status_code=500, detail="Embedding client not initialized. Check GEMINI_API_KEY.")

        # Safety: truncate texts to stay within token limits
        truncated_texts = [str(t)[:8000] for t in texts]
        
        try:
            # Gemini's embed_content returns a dictionary with an 'embedding' list of floats
            # For a batch, we can pass the whole list
            response = genai.embed_content(
                model=self.model,
                content=truncated_texts,
                task_type="retrieval_document"
            )
            return response['embedding']
        except Exception as e:
            if "403" in str(e) or "denied" in str(e).lower():
                error_msg = "Embedding API Access Denied (403). Your project may be restricted or the API key is invalid."
            else:
                error_msg = f"Embedding API Error (encode): {str(e)}"
            print(f"[EmbeddingService] {error_msg}")
            raise HTTPException(status_code=502, detail=error_msg) from e

    def encode_passage(self, texts: list[str]) -> list[list[float]]:
        """Specific method for indexing passages (document retrieval task type)."""
        if not texts:
            return []
        
        if not self.client:
            raise HTTPException(status_code=500, detail="Embedding client not initialized. Check GEMINI_API_KEY.")

        truncated_texts = [str(t)[:8000] for t in texts]
        try:
            response = genai.embed_content(
                model=self.model,
                content=truncated_texts,
                task_type="retrieval_document"
            )
            return response['embedding']
        except Exception as e:
            error_msg = f"Embedding API Error (encode_passage): {str(e)}"
            print(f"[EmbeddingService] {error_msg}")
            raise HTTPException(status_code=502, detail=error_msg) from e

# Singleton instance
embedding_service = EmbeddingService()

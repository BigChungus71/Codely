import sys
from contextlib import nullcontext
from pathlib import Path
from threading import Lock

from .gemini import ProviderError


MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
_ENCODE_LOCK = Lock()


def _encoding_threads():
    if sys.platform != "darwin":
        return nullcontext()
    from threadpoolctl import threadpool_limits

    # Apple Silicon wheels bundle separate OpenMP runtimes. Limit them during
    # encoding to avoid a native crash when a worker has already loaded FAISS.
    return threadpool_limits(limits=1, user_api="openmp")


class LocalEmbedder:
    """Encode retrieval inputs on CPU using locally downloaded model files."""

    def __init__(self, model_path: str | Path = MODEL_ID):
        self._model_path = str(model_path)
        self._model = None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            with _ENCODE_LOCK:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer

                    self._model = SentenceTransformer(
                        self._model_path, device="cpu", local_files_only=True,
                        trust_remote_code=False, token=False,
                    )
                with _encoding_threads():
                    vectors = self._model.encode(
                        texts, batch_size=32, show_progress_bar=False,
                        convert_to_numpy=True, normalize_embeddings=True,
                    )
            return vectors.tolist()
        except (ImportError, OSError, RuntimeError, TypeError, ValueError):
            raise ProviderError("Local MiniLM embedding failed or model files are unavailable") from None

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

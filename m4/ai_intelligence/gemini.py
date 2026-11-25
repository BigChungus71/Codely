import json
import os
import re
from typing import Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from .contracts import ReviewDraft


class ProviderError(RuntimeError):
    pass


class ProviderRateLimitError(ProviderError):
    status_code = 429


class Generator(Protocol):
    mode: Literal["gemini", "groq", "mock"]

    def generate(self, instruction: str, payload: dict, schema: type[BaseModel]) -> BaseModel: ...


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Gemini:
    mode = "gemini"
    base_url = "https://generativelanguage.googleapis.com/v1beta/models/"

    def __init__(self):
        load_dotenv()
        self._key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not self._key:
            raise ProviderError("Set GEMINI_API_KEY to use the live provider")
        self.model = self._model("GEMINI_MODEL", "gemini-2.5-flash")
        self.embedding_model = self._model("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        try:
            self.timeout = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "30"))
        except ValueError:
            raise ProviderError("Invalid Gemini timeout") from None
        if not 0 < self.timeout <= 120:
            raise ProviderError("Gemini timeout must be between 0 and 120 seconds")
        self._opener = build_opener(_NoRedirect())

    @staticmethod
    def _model(variable: str, default: str) -> str:
        name = os.getenv(variable, default).removeprefix("models/")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", name):
            raise ProviderError(f"Invalid model name in {variable}")
        return name

    def _request(self, suffix: str, body: dict | None = None) -> dict:
        data = None if body is None else json.dumps(body).encode()
        request = Request(self.base_url + suffix, data=data, headers={
            "x-goog-api-key": self._key, "Content-Type": "application/json",
        })
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read(8_000_001)
            if len(raw) > 8_000_000:
                raise ProviderError("Gemini response exceeded the size limit")
            return json.loads(raw)
        except HTTPError as error:
            if error.code == 429:
                raise ProviderRateLimitError("Gemini rate limit reached (HTTP 429)") from None
            raise ProviderError(f"Gemini returned HTTP {error.code}") from None
        except (URLError, TimeoutError, OSError):
            raise ProviderError("Gemini connection failed or timed out") from None
        except (ValueError, UnicodeError):
            raise ProviderError("Gemini returned invalid JSON") from None

    def check(self) -> dict:
        generation = self._request(self.model)
        embedding = self._request(self.embedding_model)
        return {
            "model": generation.get("name", self.model),
            "embedding_model": embedding.get("name", self.embedding_model),
            "reachable": True,
        }

    def generate(self, instruction, payload, schema):
        response = self._request(self.model + ":generateContent", {
            "systemInstruction": {"parts": [{"text": instruction}]},
            "contents": [{"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema.model_json_schema(),
                "temperature": 0.2,
                "maxOutputTokens": 4096,
            },
        })
        try:
            candidate = response["candidates"][0]
            if candidate.get("finishReason") != "STOP":
                raise ValueError
            text = "".join(part.get("text", "") for part in candidate["content"]["parts"]
                           if not part.get("thought"))
            return schema.model_validate_json(text)
        except (KeyError, IndexError, TypeError, AttributeError, ValueError, ValidationError):
            raise ProviderError("Gemini returned incomplete or schema-invalid output") from None

    def _embedding_request(self, text, task):
        return {
            "model": "models/" + self.embedding_model,
            "content": {"parts": [{"text": text}]},
            "taskType": task,
            "outputDimensionality": 768,
        }

    def embed_documents(self, texts):
        vectors = []
        try:
            for start in range(0, len(texts), 48):
                requests = [self._embedding_request(text, "RETRIEVAL_DOCUMENT")
                            for text in texts[start:start + 48]]
                result = self._request(self.embedding_model + ":batchEmbedContents", {"requests": requests})
                vectors.extend(item["values"] for item in result["embeddings"])
        except (KeyError, TypeError):
            raise ProviderError("Gemini returned invalid document embeddings") from None
        return vectors

    def embed_query(self, text):
        result = self._request(self.embedding_model + ":embedContent",
                               self._embedding_request(text, "RETRIEVAL_QUERY"))
        try:
            return result["embedding"]["values"]
        except (KeyError, TypeError):
            raise ProviderError("Gemini returned an invalid query embedding") from None


class MockGenerator:
    mode = "mock"

    def generate(self, instruction, payload, schema):
        if schema is not ReviewDraft:
            raise ProviderError("Provide a schema-specific offline fixture")
        evidence = payload["evidence"]
        return schema.model_validate({
            "explanation": "Offline fixture showing how a scanner finding is linked to repository evidence.",
            "root_cause": "The offline fixture does not infer a root cause.",
            "potential_impact": "Impact requires human review or a live interpretation.",
            "preconditions": [],
            "evidence_ids": [item["id"] for item in evidence[:4]],
            "affected_components": [evidence[0]["path"]],
            "recommended_remediation": "Review the scanner rule and inspect the cited source.",
            "assumptions_and_limitations": ["Mock result. Generated without contacting Gemini."],
            "contextual_concerns": [],
            "edits": [],
            "verification_steps": ["Review the cited lines against the original scanner result."],
        })

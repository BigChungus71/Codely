import json
import os

from dotenv import load_dotenv
from pydantic import ValidationError

from .gemini import ProviderError


class GroqGenerator:
    mode = "groq"
    model = "openai/gpt-oss-120b"

    def __init__(self):
        load_dotenv()
        key = os.getenv("GROQ_API_KEY", "").strip()
        if not key:
            raise ProviderError("Set GROQ_API_KEY to use Groq")
        try:
            timeout = float(os.getenv("GROQ_TIMEOUT_SECONDS", "30"))
        except ValueError:
            raise ProviderError("Invalid Groq timeout") from None
        if not 0 < timeout <= 120:
            raise ProviderError("Groq timeout must be between 0 and 120 seconds")

        try:
            import groq
            import httpx
        except ImportError:
            raise ProviderError("Install the Groq Python SDK to use Groq") from None
        self._sdk = groq
        self._client = groq.Groq(
            # The Python SDK appends /openai/v1 to the host for chat.
            api_key=key, base_url="https://api.groq.com",
            timeout=timeout, max_retries=0,
            http_client=httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False),
        )

    def close(self):
        self._client.close()

    def generate(self, instruction, payload, schema):
        try:
            result = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                response_format={"type": "json_schema", "json_schema": {
                    "name": schema.__name__, "strict": True, "schema": schema.model_json_schema(),
                }},
                reasoning_effort="low",
                max_completion_tokens=4096,
            )
        except self._sdk.RateLimitError:
            raise ProviderError("Groq rate limit reached (HTTP 429)") from None
        except self._sdk.APITimeoutError:
            raise ProviderError("Groq request timed out") from None
        except self._sdk.APIStatusError as error:
            raise ProviderError(f"Groq returned HTTP {error.status_code}") from None
        except self._sdk.APIConnectionError:
            raise ProviderError("Groq connection failed") from None
        except self._sdk.APIError:
            raise ProviderError("Groq returned an invalid API response") from None

        try:
            choice = result.choices[0]
            text = choice.message.content
            if choice.finish_reason != "stop" or not text or self._client.api_key in text:
                raise ValueError
            return schema.model_validate_json(text)
        except (AttributeError, IndexError, TypeError, ValueError, ValidationError):
            raise ProviderError("Groq returned incomplete or schema-invalid output") from None

import os

from dotenv import load_dotenv

from .gemini import Gemini, Generator, MockGenerator, ProviderError
from .groq import GroqGenerator


PROVIDERS = {"gemini": Gemini, "groq": GroqGenerator, "mock": MockGenerator}


def create_generator(provider: str | None = None) -> Generator:
    """Resolve the configured provider without falling back after a failure."""
    load_dotenv()
    name = provider if provider is not None else os.getenv("M4_PROVIDER", "mock")
    factory = PROVIDERS.get(name.strip().lower())
    if factory is None:
        raise ProviderError("M4_PROVIDER must be gemini, groq, or mock")
    return factory()

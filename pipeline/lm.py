"""DSPy LM configuration for Ollama Cloud (direct API, not the local daemon)."""

import os

import dspy
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "glm-5.2"
OLLAMA_CLOUD_BASE = "https://ollama.com/v1"


def make_lm(model: str = DEFAULT_MODEL, temperature: float = 0.0, max_tokens: int = 8000) -> dspy.LM:
    api_key = os.environ.get("OLLAMA_API_KEY")
    if not api_key:
        raise SystemExit(
            "OLLAMA_API_KEY is not set. Get a key at https://ollama.com/settings/keys "
            "and add it to .env as OLLAMA_API_KEY=... (already gitignored)."
        )
    return dspy.LM(
        f"openai/{model}",
        api_base=OLLAMA_CLOUD_BASE,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
    )

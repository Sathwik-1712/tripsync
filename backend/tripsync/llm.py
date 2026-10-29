"""LLM fallback chain: Groq -> Gemini -> local Ollama. Every caller must cope
with None (no LLM available) by falling back to rule-based logic."""
import logging
import os
from functools import lru_cache

import requests

from .config import offline

log = logging.getLogger(__name__)


LLM_TIMEOUT = 30  # seconds; a slow provider falls through to the next one


@lru_cache
def chat_models() -> list[tuple[str, object]]:
    if offline() or os.getenv("TRIPSYNC_NO_LLM") == "1":
        return []
    models = []
    if os.getenv("GROQ_API_KEY"):
        from langchain_groq import ChatGroq
        models.append(("Groq", ChatGroq(model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
                                        temperature=0, max_retries=1, timeout=LLM_TIMEOUT)))
    if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        models.append(("Gemini", ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest"), temperature=0,
            max_retries=1, timeout=LLM_TIMEOUT,
            google_api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))))
    try:
        requests.get("http://localhost:11434/api/tags", timeout=0.5)
        from langchain_ollama import ChatOllama
        models.append(("Ollama", ChatOllama(model=os.getenv("OLLAMA_MODEL", "llama3.1:8b"), temperature=0,
                                            client_kwargs={"timeout": LLM_TIMEOUT * 2})))
    except requests.RequestException:
        pass
    return models


def provider_names() -> list[str]:
    return [name for name, _ in chat_models()]


def structured(schema, prompt: str):
    """Return a `schema` instance from the first provider that answers, else None."""
    for name, model in chat_models():
        try:
            return model.with_structured_output(schema).invoke(prompt)
        except Exception as e:  # noqa: BLE001 - rate limits, bad JSON, network
            log.warning("%s structured output failed: %s", name, e)
    return None


def text(prompt: str) -> str | None:
    for name, model in chat_models():
        try:
            msg = model.invoke(prompt)
            # Gemini returns a list of content parts; `.text` flattens any provider's reply to a string.
            return msg.text if isinstance(msg.text, str) else msg.text()
        except Exception as e:  # noqa: BLE001
            log.warning("%s failed: %s", name, e)
    return None

"""LLM provider factory with automatic model fallback on rate-limit / quota / 404 errors."""
import logging
import os
import time
from typing import Any, Optional, Sequence
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from aegis_os.kernel.exceptions import KernelError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LLMError(KernelError):
    """Base exception for LLM provider errors."""

class ConfigurationError(LLMError):
    """Raised when an API key or configuration required by a provider is missing."""

class UnsupportedProviderError(LLMError):
    """Raised when an unknown model provider is requested."""

class AllModelsExhaustedError(LLMError):
    """Raised when every model in the fallback chain fails."""

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class LLMConfig(BaseSettings):
    """Configuration loaded from environment variables and .env file."""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    aegis_model_provider: str = Field(default="groq", alias="AEGIS_MODEL_PROVIDER")
    aegis_model_name: Optional[str] = Field(default=None, alias="AEGIS_MODEL_NAME")
    aegis_temperature: float = Field(default=0.0, alias="AEGIS_TEMPERATURE")
    groq_api_key: Optional[str] = Field(default=None, alias="GROQ_API_KEY")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")

# ---------------------------------------------------------------------------
# Fallback model chains — ordered best-first per provider.
# When a model returns a 400/404/429/503 error the next one is tried.
# ---------------------------------------------------------------------------

GROQ_FALLBACK_CHAIN = [
    "llama-3.3-70b-versatile",               # Primary: large 128k context
    "qwen/qwen3.8-27b",                       # Fallback 1: smaller context, capable
    "meta-llama/llama-4-scout-17b-16e-instruct",  # Fallback 2: newest scout
]

_RETRYABLE_PHRASES = [
    "decommissioned", "not found", "rate limit", "request too large",
    "context_length_exceeded", "model_not_found", "429", "404", "400", "503",
    "overloaded", "too many requests",
]


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(p in msg for p in _RETRYABLE_PHRASES)


# ---------------------------------------------------------------------------
# Fallback-aware wrapper
# ---------------------------------------------------------------------------

class FallbackChatModel(BaseChatModel):
    """
    A transparent LangChain BaseChatModel wrapper that walks a list of
    concrete models and retries on rate-limit / quota / deprecated-model errors.

    This lets any agent call `.invoke()` normally — if the first model fails
    with a retryable error, the wrapper silently swaps to the next one.
    """

    models: list[BaseChatModel] = Field(default_factory=list)
    _active_index: int = 0

    class Config:
        arbitrary_types_allowed = True

    @property
    def _llm_type(self) -> str:
        return "fallback-chain"

    def _generate(self, messages: Sequence[BaseMessage], stop: Optional[list[str]] = None, **kwargs: Any) -> ChatResult:
        last_exc: Optional[Exception] = None
        for idx, model in enumerate(self.models):
            try:
                if idx > 0:
                    logger.warning("[FallbackLLM] Switching to model index %d: %s", idx, getattr(model, 'model_name', model))
                result = model._generate(messages, stop=stop, **kwargs)
                self._active_index = idx
                return result
            except Exception as exc:
                if _is_retryable(exc):
                    logger.warning("[FallbackLLM] Model %d failed (%s), trying next…", idx, exc)
                    last_exc = exc
                    time.sleep(0.5)
                    continue
                raise  # non-retryable — propagate

        raise AllModelsExhaustedError(
            f"All models in the fallback chain failed. Last error: {last_exc}"
        )

    async def _agenerate(self, messages: Sequence[BaseMessage], stop: Optional[list[str]] = None, **kwargs: Any) -> ChatResult:
        last_exc: Optional[Exception] = None
        for idx, model in enumerate(self.models):
            try:
                result = await model._agenerate(messages, stop=stop, **kwargs)
                self._active_index = idx
                return result
            except Exception as exc:
                if _is_retryable(exc):
                    last_exc = exc
                    continue
                raise

        raise AllModelsExhaustedError(
            f"All models in the fallback chain failed. Last error: {last_exc}"
        )


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def get_llm(
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    config: Optional[LLMConfig] = None,
    model: Optional[str] = None,
) -> BaseChatModel:
    """
    Instantiate and return a LangChain chat model.

    For Groq: returns a FallbackChatModel that automatically tries the next
    model in GROQ_FALLBACK_CHAIN on any 400/404/429/503 error — including
    decommissioned models and rate-limit / context-too-large errors.

    Args:
        provider:    'groq', 'openai', or 'ollama'. Defaults to AEGIS_MODEL_PROVIDER.
        model_name:  Specific model to use (skips fallback chain).
        temperature: Sampling temperature. Default 0.0 (deterministic).
        max_tokens:  Optional token generation cap.
        config:      Optional LLMConfig. Loaded from env/dotenv if None.
        model:       Alias for model_name (for legacy callers).

    Returns:
        BaseChatModel (may be a FallbackChatModel wrapping multiple backends).

    Raises:
        ConfigurationError:      Missing API key.
        UnsupportedProviderError: Unknown provider string.
        AllModelsExhaustedError:  Every model in the chain failed immediately.
    """
    cfg = config or LLMConfig()
    active_provider = (provider or cfg.aegis_model_provider).strip().lower()
    active_temp = temperature if temperature is not None else cfg.aegis_temperature
    explicit_model = model_name or model  # caller pinned a specific model

    # ------------------------------------------------------------------
    # GROQ
    # ------------------------------------------------------------------
    if active_provider == "groq":
        api_key = cfg.groq_api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ConfigurationError(
                "GROQ_API_KEY is not set in environment or .env file. "
                "Set it or switch provider with AEGIS_MODEL_PROVIDER=ollama."
            )
        from langchain_groq import ChatGroq

        def _make_groq(model_id: str) -> ChatGroq:
            kwargs: dict = {"model": model_id, "temperature": active_temp, "groq_api_key": api_key}
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            return ChatGroq(**kwargs)

        # If caller pinned a model, honour it (no fallback).
        if explicit_model:
            logger.info("[LLM] Groq (pinned): %s", explicit_model)
            return _make_groq(explicit_model)

        # Build chain: .env AEGIS_MODEL_NAME first, then GROQ_FALLBACK_CHAIN
        preferred = cfg.aegis_model_name
        if preferred:
            chain_ids = [preferred] + [m for m in GROQ_FALLBACK_CHAIN if m != preferred]
        else:
            chain_ids = GROQ_FALLBACK_CHAIN

        chain = [_make_groq(mid) for mid in chain_ids]
        logger.info("[LLM] Groq fallback chain: %s", chain_ids)
        return FallbackChatModel(models=chain)

    # ------------------------------------------------------------------
    # OPENAI
    # ------------------------------------------------------------------
    elif active_provider == "openai":
        api_key = cfg.openai_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ConfigurationError(
                "OPENAI_API_KEY is not set in environment or .env file."
            )
        from langchain_openai import ChatOpenAI

        resolved_model = explicit_model or cfg.aegis_model_name or "gpt-4o"
        kwargs = {"model": resolved_model, "temperature": active_temp, "api_key": api_key}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        logger.info("[LLM] OpenAI: %s", resolved_model)
        return ChatOpenAI(**kwargs)

    # ------------------------------------------------------------------
    # OLLAMA — local, no rate limits, no API key required
    # ------------------------------------------------------------------
    elif active_provider == "ollama":
        from langchain_ollama import ChatOllama

        resolved_model = explicit_model or cfg.aegis_model_name or "qwen2.5-coder:7b"
        base_url = cfg.ollama_base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        logger.info("[LLM] Ollama (local): %s @ %s", resolved_model, base_url)
        return ChatOllama(model=resolved_model, temperature=active_temp, base_url=base_url)

    else:
        raise UnsupportedProviderError(
            f"Unsupported provider '{active_provider}'. "
            f"Supported: 'groq', 'openai', 'ollama'."
        )
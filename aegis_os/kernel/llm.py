import os
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import Field
from pydantic_settings import BaseSettings,SettingsConfigDict
from aegis_os.kernel.exceptions import KernelError

class LLMError(KernelError):
    """Base exception for LLM provider errors."""

class ConfigurationError(LLMError):
    """Raised when an API key or configuration required by a provider is missing."""

class UnsupportedProviderError(LLMError):
    """Raised when an unknown model provider is requested."""

class LLMConfig(BaseSettings):
    """Configuration loaded from environment variables and .env file."""
    model_config = SettingsConfigDict(env_file=".env",env_file_encoding="utf-8",extra="ignore")

    aegis_model_provider: str =Field(default="groq",alias="AEGIS_MODEL_PROVIDER")
    aegis_model_name: Optional[str] =Field(default=None,alias="AEGIS_MODEL_NAME")
    aegis_temperature: float =Field(default=0.0,alias="AEGIS_TEMPERATURE")
    groq_api_key: Optional[str] =Field(default=None,alias="GROQ_API_KEY")
    openai_api_key: Optional[str] =Field(default=None,alias="OPENAI_API_KEY")
    ollama_base_url: str =Field(default="http://localhost:11434",alias="OLLAMA_BASE_URL")

_DEFAULT_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o",
    "ollama": "qwen2.5-coder:7b",
}


def get_llm(provider: Optional[str] = None,model_name: Optional[str] = None,temperature: Optional[float] = None,max_tokens: Optional[int] = None,config: Optional[LLMConfig] = None,model: Optional[str] = None) -> BaseChatModel:
    """
    Instantiate and return a standardized LangChain chat model.
    Args:
        provider: 'groq', 'openai', or 'ollama'. Defaults to AEGIS_MODEL_PROVIDER from .env.
        model_name: Name of model. Defaults to AEGIS_MODEL_NAME or provider default.
        temperature: Sampling temperature (0.0 = deterministic). Defaults to 0.0.
        max_tokens: Optional token generation limit.
        config: Optional LLMConfig instance. If None, loaded from environment.
        model: Optional alias for model_name.
    Returns:
        Configured BaseChatModel instance.
    Raises:
        ConfigurationError: If the required API key for the selected provider is missing.
        UnsupportedProviderError: If the provider is not supported.
    """
    cfg=config or LLMConfig()

    active_provider=(provider or cfg.aegis_model_provider).strip().lower()
    active_temp=temperature if temperature is not None else cfg.aegis_temperature
    effective_model=model_name or model

    if active_provider=="groq":
        api_key=cfg.groq_api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ConfigurationError(
                "GROQ_API_KEY is not set in environment or .env file. "
                "Provide a valid key or switch provider."
            )
        from langchain_groq import ChatGroq

        resolved_model=effective_model or cfg.aegis_model_name or _DEFAULT_MODELS["groq"]
        kwargs:dict = {
            "model": resolved_model,
            "temperature": active_temp,
            "groq_api_key": api_key,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return ChatGroq(**kwargs)

    elif active_provider=="openai":
        api_key=cfg.openai_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ConfigurationError(
                "OPENAI_API_KEY is not set in environment or .env file. "
                "Provide a valid key or switch provider."
            )
        from langchain_openai import ChatOpenAI

        resolved_model=effective_model or cfg.aegis_model_name or _DEFAULT_MODELS["openai"]
        kwargs={ 
            "model": resolved_model,
            "temperature": active_temp,
            "api_key": api_key,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return ChatOpenAI(**kwargs)

    elif active_provider=="ollama":
        from langchain_ollama import ChatOllama

        resolved_model=effective_model or cfg.aegis_model_name or _DEFAULT_MODELS["ollama"]
        base_url=cfg.ollama_base_url or os.getenv("OLLAMA_BASE_URL","http://localhost:11434")
        return ChatOllama(model=resolved_model,temperature=active_temp,base_url=base_url)

    else:
        raise UnsupportedProviderError(
            f"Unsupported provider '{active_provider}'. "
            f"Supported providers are: 'groq', 'openai', 'ollama'."
        )
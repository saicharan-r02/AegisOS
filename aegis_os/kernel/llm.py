"""Configurable LLM construction with a legacy LangChain factory."""

from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from aegis_os.kernel.providers import (
    LangChainProvider,
    LLMProvider,
    ModelPricing,
    ProviderCapabilities,
    ProviderRouter,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Base exception for LLM configuration and provider errors."""


class ConfigurationError(LLMError):
    """Raised when provider configuration or credentials are missing."""


class UnsupportedProviderError(LLMError):
    """Raised when an unknown provider is requested."""


class AllModelsExhaustedError(ProviderUnavailableError, LLMError):
    """Raised when all configured fallback models fail."""


class LLMConfig(BaseSettings):
    """Legacy environment configuration retained for existing callers."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    aegis_model_provider: str = Field(default="groq", alias="AEGIS_MODEL_PROVIDER")
    aegis_model_name: str | None = Field(default=None, alias="AEGIS_MODEL_NAME")
    aegis_temperature: float = Field(default=0.0, alias="AEGIS_TEMPERATURE")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    google_api_key: str | None = Field(default=None, alias="GOOGLE_API_KEY")
    openai_compatible_api_key: str | None = Field(
        default=None, alias="OPENAI_COMPATIBLE_API_KEY"
    )
    openai_compatible_base_url: str | None = Field(
        default=None, alias="OPENAI_COMPATIBLE_BASE_URL"
    )
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")


class ModelSpec(BaseModel):
    """One provider/model entry in a role's ordered fallback chain."""

    model_config = ConfigDict(extra="ignore")

    provider: str
    model: str
    base_url: str | None = None
    api_key_env: str | None = None
    native_tool_calling: bool = True


class RoleModelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str
    model: str
    fallback: list[ModelSpec] = Field(default_factory=list)
    native_tool_calling: bool = True
    context_tokens: int = 32_000
    max_tool_output_tokens: int = 2_000


class RuntimeLLMConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    default_provider: str = "groq"
    default_model: str | None = None
    temperature: float = 0.0
    request_timeout_seconds: float = 45.0
    max_retries: int = 2
    retry_base_seconds: float = 0.25
    retry_max_seconds: float = 4.0
    circuit_cooldown_seconds: float = 30.0
    max_tokens: int = 200_000
    max_cost_usd: float | None = 2.0
    max_wall_seconds: float | None = 1800.0
    max_completion_tokens: int = 2_048
    roles: dict[str, RoleModelConfig] = Field(default_factory=dict)
    pricing: dict[str, ModelPricing] = Field(default_factory=dict)


def _default_config_path() -> Path:
    current = Path.cwd() / "aegis.toml"
    if current.is_file():
        return current
    return Path(__file__).resolve().parents[2] / "aegis.toml"


def load_runtime_config(config_path: Path | None = None) -> RuntimeLLMConfig:
    """Load and validate LLM routing config from `aegis.toml`."""
    path = config_path or _default_config_path()
    if not path.is_file():
        return RuntimeLLMConfig()
    try:
        with path.open("rb") as config_file:
            raw = tomllib.load(config_file)
        llm_section: dict[str, Any] = raw.get("llm", {})
        roles_raw = llm_section.get("roles", {})
        pricing_raw = llm_section.get("pricing", {})
        roles = {str(name).upper(): RoleModelConfig.model_validate(value) for name, value in roles_raw.items()}
        pricing = {str(name): ModelPricing(**value) for name, value in pricing_raw.items()}
        return RuntimeLLMConfig.model_validate(
            {**llm_section, "roles": roles, "pricing": pricing}
        )
    except (OSError, tomllib.TOMLDecodeError, ValueError) as exc:
        raise ConfigurationError(f"Unable to load LLM configuration from {path}: {exc}") from exc


def _api_key(config: LLMConfig, provider: str, api_key_env: str | None = None) -> str | None:
    env_name = api_key_env or {
        "groq": "GROQ_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GOOGLE_API_KEY",
        "openai_compatible": "OPENAI_COMPATIBLE_API_KEY",
    }.get(provider)
    configured = {
        "groq": config.groq_api_key,
        "openai": config.openai_api_key,
        "anthropic": config.anthropic_api_key,
        "gemini": config.google_api_key,
        "openai_compatible": config.openai_compatible_api_key,
    }.get(provider)
    return configured or (os.getenv(env_name) if env_name else None)


def _build_model(
    spec: ModelSpec,
    *,
    settings: LLMConfig,
    temperature: float,
    max_tokens: int | None,
    timeout_seconds: float,
) -> BaseChatModel:
    provider = spec.provider.strip().lower()
    model_id = spec.model.strip()
    if not model_id:
        raise ConfigurationError(f"Model ID is empty for provider '{provider}'.")

    key = _api_key(settings, provider, spec.api_key_env)
    common: dict[str, Any] = {"temperature": temperature}
    if max_tokens is not None:
        token_field={"gemini":"max_output_tokens","ollama":"num_predict"}.get(provider,"max_tokens")
        common[token_field]=max_tokens

    if provider == "groq":
        if not key:
            raise ConfigurationError("GROQ_API_KEY is not set in environment or .env file.")
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=model_id,
            api_key=SecretStr(key),
            timeout=timeout_seconds,
            max_retries=0,
            **common,
        )
    if provider == "openai":
        if not key:
            raise ConfigurationError("OPENAI_API_KEY is not set in environment or .env file.")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_id,
            api_key=SecretStr(key),
            timeout=timeout_seconds,
            max_retries=0,
            **common,
        )
    if provider == "openai_compatible":
        base_url = spec.base_url or settings.openai_compatible_base_url
        if not base_url:
            raise ConfigurationError(
                "An OpenAI-compatible endpoint requires a base_url in aegis.toml or "
                "OPENAI_COMPATIBLE_BASE_URL."
            )
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_id,
            base_url=base_url,
            api_key=SecretStr(key or "local"),
            timeout=timeout_seconds,
            max_retries=0,
            **common,
        )
    if provider == "anthropic":
        if not key:
            raise ConfigurationError("ANTHROPIC_API_KEY is not set in environment or .env file.")
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model_name=model_id,
            api_key=SecretStr(key),
            timeout=timeout_seconds,
            max_retries=0,
            **common,
        )
    if provider == "gemini":
        if not key:
            raise ConfigurationError("GOOGLE_API_KEY is not set in environment or .env file.")
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_id,
            google_api_key=key,
            timeout=timeout_seconds,
            max_retries=0,
            **common,
        )
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=model_id,
            base_url=settings.ollama_base_url,
            client_kwargs={"timeout": timeout_seconds},
            **common,
        )
    raise UnsupportedProviderError(
        f"Unsupported provider '{provider}'. Supported: groq, openai, anthropic, gemini, "
        "openai_compatible, ollama."
    )


def _to_provider(spec: ModelSpec, model: BaseChatModel, config: RuntimeLLMConfig) -> LLMProvider:
    price = config.pricing.get(f"{spec.provider}/{spec.model}")
    capabilities=ProviderCapabilities(
        native_tool_calling=spec.native_tool_calling,
        streaming=callable(getattr(model,"stream",None)),
        token_counting=callable(getattr(model,"get_num_tokens_from_messages",None)),
        prompt_caching=spec.provider.lower()=="openai",
    )
    return LangChainProvider(
        provider_name=spec.provider,
        model_name=spec.model,
        model=model,
        pricing=price,
        capabilities=capabilities,
    )


def get_llm(
    provider: str | None = None,
    model_name: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    config: LLMConfig | None = None,
    model: str | None = None,
    role: Any | None = None,
    config_path: Path | None = None,
    workspace_root: Path | None = None,
) -> BaseChatModel | ProviderRouter:
    """Create a configured chat model, retaining the historical factory API.

    Passing a role activates its configured ordered fallback chain and resilience
    router. Calls without a role continue to return the raw LangChain model.
    """
    settings = config or LLMConfig()
    if config_path is None and workspace_root is not None:
        project_config=Path(workspace_root)/"aegis.toml"
        if project_config.is_file():
            config_path=project_config
    runtime = load_runtime_config(config_path)
    role_name = getattr(role, "value", role)
    default_temperature=runtime.temperature if role_name is not None else settings.aegis_temperature
    resolved_temperature = temperature if temperature is not None else default_temperature
    resolved_max_tokens=max_tokens if max_tokens is not None else runtime.max_completion_tokens
    legacy_model = model_name or model

    role_config = runtime.roles.get(str(role_name).upper()) if role_name is not None else None
    if role_config is None:
        resolved_provider = (provider or settings.aegis_model_provider or runtime.default_provider).lower()
        resolved_model = legacy_model or settings.aegis_model_name or runtime.default_model
        if resolved_model is None:
            raise ConfigurationError(
                "No model ID is configured. Set a default in aegis.toml or pass model_name."
            )
        spec = ModelSpec(provider=resolved_provider, model=resolved_model)
        return _build_model(
            spec,
            settings=settings,
            temperature=resolved_temperature,
            max_tokens=resolved_max_tokens,
            timeout_seconds=runtime.request_timeout_seconds,
        )

    primary = ModelSpec(
        provider=(provider or role_config.provider).lower(),
        model=legacy_model or role_config.model,
        native_tool_calling=role_config.native_tool_calling,
    )
    specs = [primary, *role_config.fallback]
    if runtime.max_cost_usd is not None:
        missing_prices=[
            f"{spec.provider}/{spec.model}"
            for spec in specs
            if f"{spec.provider}/{spec.model}" not in runtime.pricing
        ]
        if missing_prices:
            raise ConfigurationError(
                "A dollar budget is enabled but pricing is missing for: "
                + ", ".join(missing_prices)
                + ". Add prices to aegis.toml or remove those models from the fallback chain."
            )
    providers: list[LLMProvider] = []
    for spec in specs:
        try:
            model_instance = _build_model(
                spec,
                settings=settings,
                temperature=resolved_temperature,
                max_tokens=resolved_max_tokens,
                timeout_seconds=runtime.request_timeout_seconds,
            )
        except (ConfigurationError, UnsupportedProviderError):
            if spec is primary:
                raise
            logger.warning("Skipping unavailable fallback provider '%s'.", spec.provider)
            continue
        providers.append(_to_provider(spec, model_instance, runtime))

    if not providers:
        raise ConfigurationError(f"No usable LLM providers are configured for role {role_name}.")
    return ProviderRouter(
        providers,
        max_retries=runtime.max_retries,
        retry_base_seconds=runtime.retry_base_seconds,
        retry_max_seconds=runtime.retry_max_seconds,
        circuit_cooldown_seconds=runtime.circuit_cooldown_seconds,
        pricing=runtime.pricing,
        context_tokens=role_config.context_tokens,
        max_tool_output_tokens=role_config.max_tool_output_tokens,
        max_completion_tokens=runtime.max_completion_tokens,
    )

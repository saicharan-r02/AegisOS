from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError


class FallbackModelConfig(BaseModel):
    provider: str
    model: str
    base_url: str | None = None
    api_key_env: str | None = None
    native_tool_calling: bool = True

class RoleLLMConfig(BaseModel):
    provider: str
    model: str
    native_tool_calling: bool = True
    context_tokens: int = Field(default=100_000, ge=1000)
    max_tool_output_tokens: int = Field(default=2000, ge=100)
    fallback: list[FallbackModelConfig] = Field(default_factory=list)

class LLMGlobalConfig(BaseModel):
    default_provider: str
    default_model: str
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    request_timeout_seconds: float = Field(default=45.0, ge=1.0)
    max_retries: int = Field(default=2, ge=0)
    max_tokens: int = Field(default=200_000, ge=1000)
    max_cost_usd: float = Field(default=2.0, ge=0.0)
    max_wall_seconds: float = Field(default=1800.0, ge=10.0)
    roles: dict[str, RoleLLMConfig] = Field(default_factory=dict)

class AegisTomlSchema(BaseModel):
    llm: LLMGlobalConfig

def validate_config_file(path: Path | str) -> tuple[bool, list[str]]:
    """
    Validate an aegis.toml configuration file against the canonical schema.
    Returns (is_valid, list_of_errors_or_warnings).
    """
    cfg_path = Path(path).resolve()
    if not cfg_path.exists():
        return False, [f"Configuration file '{cfg_path}' does not exist."]

    try:
        with open(cfg_path, "rb") as f:
            raw_data = tomllib.load(f)
    except Exception as exc:
        return False, [f"TOML syntax error: {exc}"]

    try:
        AegisTomlSchema.model_validate(raw_data)
        messages = [
            f"Configuration '{cfg_path.name}' is valid.",
            f"Default provider: {raw_data.get('llm', {}).get('default_provider')}",
            f"Roles configured: {len(raw_data.get('llm', {}).get('roles', {}))}",
        ]
        return True, messages
    except ValidationError as val_err:
        errors = [f"{err['loc']}: {err['msg']}" for err in val_err.errors()]
        return False, errors

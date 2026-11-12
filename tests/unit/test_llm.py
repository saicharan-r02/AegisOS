
from pathlib import Path

import pytest

from aegis_os.kernel.llm import (
    ConfigurationError,
    LLMConfig,
    UnsupportedProviderError,
    get_llm,
    load_runtime_config,
)
from aegis_os.kernel.providers import ProviderRouter
from aegis_os.kernel.state import AgentRole

NVIDIA_ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"
NVIDIA_LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"


class TestLLMFactory:
    """Tests for NVIDIA-only initialization and configuration validation."""

    def test_missing_nvidia_api_key_raises_configuration_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        cfg = LLMConfig(
            NVIDIA_API_KEY=None,
            AEGIS_MODEL_PROVIDER="nvidia",
        )

        with pytest.raises(ConfigurationError) as exc_info:
            get_llm(
                provider="nvidia",
                model_name="test-model",
                config=cfg,
            )

        assert "NVIDIA_API_KEY" in str(exc_info.value)

    def test_unsupported_provider_raises_error(self) -> None:
        with pytest.raises(UnsupportedProviderError) as exc_info:
            get_llm(
                provider="invalid_ai_service",
                model_name="test-model",
                config=LLMConfig(NVIDIA_API_KEY="nvapi-mock-test-key"),
            )

        assert "Unsupported provider 'invalid_ai_service'" in str(exc_info.value)

    @pytest.mark.parametrize(
        "provider",
        [
            "groq",
            "ollama",
            "openai",
            "anthropic",
            "gemini",
            "openai_compatible",
        ],
    )
    def test_removed_providers_are_unsupported(self, provider: str) -> None:
        with pytest.raises(UnsupportedProviderError):
            get_llm(
                provider=provider,
                model_name="any-model",
                config=LLMConfig(NVIDIA_API_KEY="nvapi-mock-test-key"),
            )

    def test_nvidia_initialization_with_key(self) -> None:
        from langchain_openai import ChatOpenAI

        cfg = LLMConfig(
            NVIDIA_API_KEY="nvapi-mock-test-key",
            AEGIS_MODEL_PROVIDER="nvidia",
        )

        llm = get_llm(
            provider="nvidia",
            model_name=NVIDIA_ULTRA,
            temperature=0.2,
            config=cfg,
        )

        assert isinstance(llm, ChatOpenAI)
        assert llm.model_name == NVIDIA_ULTRA
        assert llm.temperature == 0.2

    def test_model_keyword_argument_alias(self) -> None:
        from langchain_openai import ChatOpenAI

        cfg = LLMConfig(
            NVIDIA_API_KEY="nvapi-mock-test-key",
            AEGIS_MODEL_PROVIDER="nvidia",
        )

        llm = get_llm(
            provider="nvidia",
            model=NVIDIA_LIGHTNING,
            config=cfg,
        )

        assert isinstance(llm, ChatOpenAI)
        assert llm.model_name == NVIDIA_LIGHTNING

    def test_role_config_builds_ordered_fallback_chain(
        self, tmp_path: Path
    ) -> None:
        config_path = tmp_path / "aegis.toml"
        config_path.write_text(
            f"""
[llm]
default_provider = "nvidia"
max_cost_usd = 0

[llm.roles.CTO]
provider = "nvidia"
model = "{NVIDIA_ULTRA}"
fallback = [
    {{ provider = "nvidia", model = "{NVIDIA_LIGHTNING}" }}
]
""",
            encoding="utf-8",
        )

        cfg = LLMConfig(
            NVIDIA_API_KEY="nvapi-mock-test-key",
            AEGIS_MODEL_PROVIDER="nvidia",
        )

        router = get_llm(
            config=cfg,
            role=AgentRole.CTO,
            config_path=config_path,
        )

        assert isinstance(router, ProviderRouter)
        assert router.model_name == NVIDIA_ULTRA
        assert [provider.model_name for provider in router.providers] == [
            NVIDIA_ULTRA,
            NVIDIA_LIGHTNING,
        ]

    def test_runtime_config_contains_role_context_and_budget_defaults(
        self, tmp_path: Path
    ) -> None:
        config_path = tmp_path / "aegis.toml"
        config_path.write_text(
            f"""
[llm]
default_provider = "nvidia"
max_tokens = 200000
max_cost_usd = 2.0

[llm.roles.DEV]
provider = "nvidia"
model = "{NVIDIA_ULTRA}"
context_tokens = 100000

[llm.roles.QA]
provider = "nvidia"
model = "{NVIDIA_LIGHTNING}"
""",
            encoding="utf-8",
        )

        runtime = load_runtime_config(config_path)

        assert runtime.max_tokens == 200_000
        assert runtime.max_cost_usd == 2.0
        assert runtime.roles["DEV"].context_tokens == 100_000
        assert runtime.roles["QA"].model == NVIDIA_LIGHTNING

    def test_zero_budget_means_no_dollar_limit(self, tmp_path: Path) -> None:
        config_path = tmp_path / "aegis.toml"
        config_path.write_text(
            """
[llm]
max_cost_usd = 0
""",
            encoding="utf-8",
        )

        runtime = load_runtime_config(config_path)

        assert runtime.max_cost_usd is None

    def test_role_routing_reads_workspace_aegis_toml(
        self, tmp_path: Path
    ) -> None:
        config_path = tmp_path / "aegis.toml"
        config_path.write_text(
            f"""
[llm]
default_provider = "nvidia"
max_cost_usd = 1.0

[llm.roles.DEV]
provider = "nvidia"
model = "{NVIDIA_ULTRA}"
fallback = []

[llm.pricing."nvidia/{NVIDIA_ULTRA}"]
input_per_million = 1.0
output_per_million = 2.0
""",
            encoding="utf-8",
        )

        cfg = LLMConfig(
            NVIDIA_API_KEY="nvapi-mock-test-key",
            AEGIS_MODEL_PROVIDER="nvidia",
        )

        router = get_llm(
            config=cfg,
            role=AgentRole.DEV,
            workspace_root=tmp_path,
        )

        assert isinstance(router, ProviderRouter)
        assert router.model_name == NVIDIA_ULTRA

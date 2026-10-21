import sys
from pathlib import Path
from types import ModuleType
from typing import Any

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


class TestLLMFactory:
    """Tests for multi-provider initialization and configuration validation."""

    def test_missing_groq_api_key_raises_configuration_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GROQ_API_KEY",raising=False)
        cfg=LLMConfig(GROQ_API_KEY=None,AEGIS_MODEL_PROVIDER="groq")

        with pytest.raises(ConfigurationError) as exc_info:
            get_llm(provider="groq",config=cfg)
        assert "GROQ_API_KEY is not set" in str(exc_info.value)

    def test_missing_openai_api_key_raises_configuration_error(self,monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY",raising=False)
        cfg=LLMConfig(OPENAI_API_KEY=None,AEGIS_MODEL_PROVIDER="openai")

        with pytest.raises(ConfigurationError) as exc_info:
            get_llm(provider="openai",config=cfg)
        assert "OPENAI_API_KEY is not set" in str(exc_info.value)

    def test_unsupported_provider_raises_error(self) -> None:
        with pytest.raises(UnsupportedProviderError) as exc_info:
            get_llm(provider="invalid_ai_service")
        assert "Unsupported provider 'invalid_ai_service'" in str(exc_info.value)

    def test_groq_initialization_with_key(self) -> None:
        cfg=LLMConfig(GROQ_API_KEY="gsk_mock_test_key_12345",AEGIS_MODEL_PROVIDER="groq")
        llm=get_llm(provider="groq",model_name="llama-3.3-70b-versatile",temperature=0.2,config=cfg)

        from langchain_groq import ChatGroq
        assert isinstance(llm,ChatGroq)
        assert llm.model_name=="llama-3.3-70b-versatile"
        assert llm.temperature==0.2

    def test_openai_initialization_with_key(self) -> None:
        cfg=LLMConfig(OPENAI_API_KEY="sk-mock-test-key-12345",AEGIS_MODEL_PROVIDER="openai")
        llm=get_llm(provider="openai",model_name="gpt-4o",temperature=0.7,config=cfg)

        from langchain_openai import ChatOpenAI
        assert isinstance(llm,ChatOpenAI)
        assert llm.model_name=="gpt-4o"
        assert llm.temperature==0.7

    def test_ollama_initialization(self) -> None:
        cfg=LLMConfig(OLLAMA_BASE_URL="http://localhost:11434",AEGIS_MODEL_PROVIDER="ollama")
        llm=get_llm(provider="ollama",model_name="qwen2.5-coder:7b",config=cfg)

        from langchain_ollama import ChatOllama
        assert isinstance(llm,ChatOllama)
        assert llm.model=="qwen2.5-coder:7b"

    def test_model_keyword_argument_alias(self) -> None:
        cfg=LLMConfig(OPENAI_API_KEY="sk-mock-test-key-12345",AEGIS_MODEL_PROVIDER="openai")
        llm=get_llm(provider="openai",model="gpt-4o",config=cfg)

        from langchain_openai import ChatOpenAI
        assert isinstance(llm,ChatOpenAI)
        assert llm.model_name=="gpt-4o"

    def test_role_config_builds_ordered_fallback_chain(self) -> None:
        cfg=LLMConfig(GROQ_API_KEY="gsk-mock-test-key",AEGIS_MODEL_PROVIDER="groq")

        router=get_llm(config=cfg,role=AgentRole.CTO)

        assert isinstance(router,ProviderRouter)
        assert router.model_name=="qwen/qwen3.8-27b"
        assert [provider.model_name for provider in router.providers]==[
            "qwen/qwen3.8-27b",
            "openai/gpt-oss-20b",
        ]

    def test_runtime_config_contains_role_context_and_budget_defaults(self) -> None:
        runtime=load_runtime_config()

        assert runtime.max_tokens==200_000
        assert runtime.max_cost_usd==2.0
        assert runtime.roles["DEV"].context_tokens==100_000
        assert runtime.roles["QA"].model=="openai/gpt-oss-20b"

    def test_role_routing_reads_workspace_aegis_toml(self,tmp_path: Path) -> None:
        (tmp_path/"aegis.toml").write_text(
            """
[llm]
default_provider = "groq"
max_cost_usd = 1.0

[llm.roles.DEV]
provider = "groq"
model = "workspace-model"
fallback = []

[llm.pricing."groq/workspace-model"]
input_per_million = 1.0
output_per_million = 2.0
""",
            encoding="utf-8",
        )
        config=LLMConfig(GROQ_API_KEY="gsk-workspace-test")

        router=get_llm(config=config,role=AgentRole.DEV,workspace_root=tmp_path)

        assert isinstance(router,ProviderRouter)
        assert router.model_name=="workspace-model"
        assert len(router.providers)==1

    @pytest.mark.parametrize(
        ("provider","module_name","class_name","key_name","key_value","extra"),
        [
            ("anthropic","langchain_anthropic","ChatAnthropic","ANTHROPIC_API_KEY","test-key",{}),
            ("gemini","langchain_google_genai","ChatGoogleGenerativeAI","GOOGLE_API_KEY","test-key",{}),
            (
                "openai_compatible",
                "langchain_openai",
                "ChatOpenAI",
                "OPENAI_COMPATIBLE_API_KEY",
                "local-key",
                {"OPENAI_COMPATIBLE_BASE_URL":"http://localhost:1234/v1"},
            ),
        ],
    )
    def test_additional_provider_factories(self,monkeypatch,provider:str,module_name:str,class_name:str,key_name:str,key_value:str,extra:dict[str,Any]) -> None:
        captured:dict[str,Any]={}

        def create_model(**kwargs:Any) -> object:
            captured.update(kwargs)
            return object()

        module=ModuleType(module_name)
        setattr(module,class_name,create_model)
        monkeypatch.setitem(sys.modules,module_name,module)
        config=LLMConfig(**{key_name:key_value,**extra})

        model=get_llm(provider=provider,model_name="configured-model",config=config)

        assert model is not None
        assert captured.get("model",captured.get("model_name"))=="configured-model"
        if provider=="openai_compatible":
            assert captured["base_url"]=="http://localhost:1234/v1"

    def test_real_anthropic_gemini_and_openai_compatible_wrappers_construct(self) -> None:
        from langchain_anthropic import ChatAnthropic
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_openai import ChatOpenAI

        anthropic=get_llm(
            provider="anthropic",
            model_name="configured-anthropic-model",
            config=LLMConfig(ANTHROPIC_API_KEY="test-anthropic-key"),
        )
        gemini=get_llm(
            provider="gemini",
            model_name="configured-gemini-model",
            config=LLMConfig(GOOGLE_API_KEY="test-google-key"),
        )
        compatible=get_llm(
            provider="openai_compatible",
            model_name="local-coder",
            config=LLMConfig(OPENAI_COMPATIBLE_BASE_URL="http://localhost:1234/v1"),
        )

        assert isinstance(anthropic,ChatAnthropic)
        assert isinstance(gemini,ChatGoogleGenerativeAI)
        assert isinstance(compatible,ChatOpenAI)
        assert compatible.openai_api_base=="http://localhost:1234/v1"

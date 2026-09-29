import pytest
from aegis_os.kernel.llm import ConfigurationError,LLMConfig,UnsupportedProviderError,get_llm

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
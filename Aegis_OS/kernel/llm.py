import os
from typing import Optional
from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel

load_dotenv()


def get_llm(
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: float = 0.0
) -> BaseChatModel:
    """
    Factory function to initialize and return the configured LLM provider.
    Reads defaults from environment variables if not passed explicitly.
    """
    provider = (provider or os.getenv("AEGIS_MODEL_PROVIDER", "groq")).lower()
    model_name = model_name or os.getenv("AEGIS_MODEL_NAME")

    if provider == "groq":
        from langchain_groq import ChatGroq
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set in environment variables.")
        return ChatGroq(
            model=model_name or "llama-3.3-70b-versatile",
            temperature=temperature,
            api_key=api_key
        )

    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set in environment variables.")
        return ChatOpenAI(
            model=model_name or "gpt-4o",
            temperature=temperature,
            api_key=api_key
        )

    elif provider == "ollama":
        from langchain_community.chat_models import ChatOllama
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return ChatOllama(
            model=model_name or "qwen2.5-coder:7b",
            temperature=temperature,
            base_url=base_url
        )

    else:
        raise ValueError(f"Unsupported provider '{provider}'.Choose from: 'groq','openai','ollama'.")

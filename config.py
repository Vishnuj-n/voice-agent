from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Postgres ---
    database_url: str = Field(
        default="postgresql://postgres:password@localhost:5432/voice_agent"
    )

    # --- Groq (LLM + STT) ---
    groq_api_key: str
    groq_llm_model: str = "llama-3.3-70b-versatile"
    groq_stt_model: str = "whisper-large-v3-turbo"

    # --- Cartesia (TTS) ---
    cartesia_api_key: str
    cartesia_voice_id: str
    cartesia_model_id: str = "sonic-3.5"

    # --- OpenAI (Embeddings) ---
    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-small"

    # --- Bot ---
    default_bot: str = "healthcare"

    # --- CORS ---
    web_origin: str = "http://localhost:3000"

    @property
    def provider_llm(self) -> str:
        return f"groq:{self.groq_llm_model}"

    @property
    def provider_stt(self) -> str:
        return f"groq:{self.groq_stt_model}"

    @property
    def provider_tts(self) -> str:
        return f"cartesia:{self.cartesia_voice_id}"

    @property
    def provider_embedding(self) -> str:
        return f"openai:{self.openai_embedding_model}"


@lru_cache
def load_config() -> Settings:
    return Settings()


def get_provider_string(role: str) -> str:
    """Return the 'provider:model' string for a given role."""
    cfg = load_config()
    mapping = {
        "llm": cfg.provider_llm,
        "stt": cfg.provider_stt,
        "tts": cfg.provider_tts,
        "embedding": cfg.provider_embedding,
    }
    if role not in mapping:
        raise ValueError(f"Unknown provider role: {role!r}")
    return mapping[role]

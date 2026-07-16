from config import get_provider_string
from providers.base import LLMProvider, STTProvider, TTSProvider
from providers.cartesia import CartesiaTTS
from providers.groq import GroqLLM, GroqWhisperSTT


def get_stt_provider() -> STTProvider:
    """
    Instantiate and return the STT provider configured in Settings.

    :return: STTProvider instance.
    """
    provider_str = get_provider_string("stt")
    parts = provider_str.split(":", 1)
    provider_type = parts[0]
    model = parts[1] if len(parts) > 1 else None

    if provider_type == "groq":
        return GroqWhisperSTT(model=model)
    else:
        raise ValueError(f"Unsupported STT provider: {provider_type}")


def get_tts_provider() -> TTSProvider:
    """
    Instantiate and return the TTS provider configured in Settings.

    :return: TTSProvider instance.
    """
    provider_str = get_provider_string("tts")
    parts = provider_str.split(":", 1)
    provider_type = parts[0]
    voice_id = parts[1] if len(parts) > 1 else None

    if provider_type == "cartesia":
        return CartesiaTTS(voice_id=voice_id)
    else:
        raise ValueError(f"Unsupported TTS provider: {provider_type}")


def get_llm_provider() -> LLMProvider:
    """
    Instantiate and return the LLM provider configured in Settings.

    :return: LLMProvider instance.
    """
    provider_str = get_provider_string("llm")
    parts = provider_str.split(":", 1)
    provider_type = parts[0]
    model = parts[1] if len(parts) > 1 else None

    if provider_type == "groq":
        return GroqLLM(model=model)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider_type}")

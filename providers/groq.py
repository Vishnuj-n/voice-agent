import io
import os
from groq import AsyncGroq
from pipecat.services.groq.stt import GroqSTTService
from pydantic_ai.models import Model
from pydantic_ai.models.groq import GroqModel

from config import load_config
from providers.base import LLMProvider, STTProvider


class GroqWhisperSTT(STTProvider):
    """Groq Speech-to-Text provider utilizing the official Groq SDK and exposing a Pipecat service."""

    def __init__(self, model: str | None = None):
        cfg = load_config()
        self.model = model or cfg.groq_stt_model

        # Ensure environment variable is set for both raw SDK client and Pipecat service
        if cfg.groq_api_key:
            os.environ["GROQ_API_KEY"] = cfg.groq_api_key

        # Official client used for Sprint 1 / Sprint 2 direct calls
        self.client = AsyncGroq(api_key=cfg.groq_api_key)

        # Configured Pipecat service instance exposed for Sprint 3
        self.service = GroqSTTService(
            api_key=cfg.groq_api_key,
            settings=GroqSTTService.Settings(model=self.model),
        )

    async def transcribe(self, audio_data: bytes) -> str:
        """
        Transcribe audio bytes using the official Groq client.

        :param audio_data: Audio file bytes.
        :return: Transcription string.
        """
        # Create a file-like object with a dummy filename so Groq's API recognizes the type
        audio_file = io.BytesIO(audio_data)
        audio_file.name = "audio.wav"

        response = await self.client.audio.transcriptions.create(
            file=audio_file,
            model=self.model,
            response_format="json",
            language="en",
        )
        return response.text


class GroqLLM(LLMProvider):
    """Groq Language Model provider utilizing PydanticAI."""

    def __init__(self, model: str | None = None):
        cfg = load_config()
        self.model = model or cfg.groq_llm_model

        # Ensure environment variable is set for PydanticAI GroqModel lookup
        if cfg.groq_api_key:
            os.environ["GROQ_API_KEY"] = cfg.groq_api_key

        self.groq_model = GroqModel(
            model_name=self.model,
        )

    def get_model(self) -> Model:
        """
        Return the configured PydanticAI GroqModel.

        :return: Model instance.
        """
        return self.groq_model

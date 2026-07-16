from abc import ABC, abstractmethod
from typing import AsyncIterator
from pydantic_ai.models import Model


class Transport(ABC):
    """Abstract base class representing an audio transport (e.g., local mic/speaker, Twilio)."""

    @abstractmethod
    async def start(self) -> None:
        """Initialize and start the transport."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop and clean up the transport."""
        pass

    @abstractmethod
    async def read_audio(self) -> bytes:
        """Read audio input (e.g., from microphone)."""
        pass

    @abstractmethod
    async def write_audio(self, audio_data: bytes) -> None:
        """Write audio output (e.g., to speaker)."""
        pass


class STTProvider(ABC):
    """Abstract base class representing a Speech-to-Text provider."""

    @abstractmethod
    async def transcribe(self, audio_data: bytes) -> str:
        """
        Transcribe the provided audio data into text.

        :param audio_data: Raw audio file bytes (e.g., WAV, MP3).
        :return: Transcribed text.
        """
        pass


class TTSProvider(ABC):
    """Abstract base class representing a Text-to-Speech provider."""

    @abstractmethod
    async def generate_speech(self, text: str) -> bytes:
        """
        Synthesize the full text into speech.

        :param text: Text to synthesize.
        :return: Audio bytes (WAV or another playable format).
        """
        pass

    @abstractmethod
    async def generate_speech_stream(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
        """
        Synthesize a stream of text chunks into a stream of audio bytes.

        :param text_stream: Async iterator yielding text chunks.
        :return: Async iterator yielding audio chunks.
        """
        pass


class LLMProvider(ABC):
    """Abstract base class representing a Language Model provider."""

    @abstractmethod
    def get_model(self) -> Model:
        """
        Return the PydanticAI Model instance.

        :return: A PydanticAI Model.
        """
        pass


class EmbeddingProvider(ABC):
    """Abstract base class representing a text embedding provider."""

    @abstractmethod
    async def get_embedding(self, text: str) -> list[float]:
        """
        Generate embedding vector for a single text.

        :param text: The input string.
        :return: List of floats representing the embedding vector.
        """
        pass

    @abstractmethod
    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embedding vectors for multiple texts.

        :param texts: List of input strings.
        :return: List of lists of floats representing embedding vectors.
        """
        pass

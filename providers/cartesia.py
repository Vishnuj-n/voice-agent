import os
from typing import AsyncIterator
from cartesia import AsyncCartesia
from pipecat.services.cartesia.tts import CartesiaTTSService

from config import load_config
from providers.base import TTSProvider


class CartesiaTTS(TTSProvider):
    """Cartesia Text-to-Speech provider utilizing the official AsyncCartesia SDK and exposing a Pipecat service."""

    def __init__(self, voice_id: str | None = None, model_id: str | None = None):
        cfg = load_config()
        self.voice_id = voice_id or cfg.cartesia_voice_id
        self.model_id = model_id or cfg.cartesia_model_id
        
        # Official async client used for direct calls in Sprint 1 / Sprint 2
        self.client = AsyncCartesia(api_key=cfg.cartesia_api_key)

        # Configured Pipecat service instance exposed for Sprint 3
        self.service = CartesiaTTSService(
            api_key=cfg.cartesia_api_key,
            voice=self.voice_id,
            model=self.model_id,
        )

    async def generate_speech(self, text: str) -> bytes:
        """
        Synthesize text into speech and return full WAV audio bytes.

        :param text: Text to synthesize.
        :return: WAV audio bytes.
        """
        response = await self.client.tts.generate(
            model_id=self.model_id,
            transcript=text,
            voice={
                "mode": "id",
                "id": self.voice_id,
            },
            output_format={
                "container": "wav",
                "sample_rate": 44100,
                "encoding": "pcm_f32le",
            },
        )
        return await response.read()

    async def generate_speech_stream(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
        """
        Stream text chunks to Cartesia via WebSocket and yield synthesised audio chunks.

        :param text_stream: Async iterator of text chunks.
        :return: Async iterator of raw audio bytes.
        """
        async with self.client.tts.websocket_connect() as connection:
            ctx = connection.context(
                model_id=self.model_id,
                voice={"mode": "id", "id": self.voice_id},
                output_format={"container": "raw", "sample_rate": 44100, "encoding": "pcm_f32le"},
            )

            # Push text chunks to Cartesia as they become available
            async for chunk in text_stream:
                await ctx.send(model_id=self.model_id, transcript=chunk, continue_=True)

            await ctx.no_more_inputs()

            # Retrieve and yield audio frames from Cartesia
            async for output in ctx.receive():
                if "audio" in output:
                    yield output["audio"]

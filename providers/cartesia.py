import asyncio
from typing import AsyncIterator
from cartesia import AsyncCartesia

from config import load_config
from providers.base import TTSProvider, AudioFormat


class CartesiaTTS(TTSProvider):
    """Cartesia Text-to-Speech provider using the official AsyncCartesia SDK."""

    @property
    def audio_format(self) -> AudioFormat:
        return AudioFormat(sample_rate=44100, num_channels=1, dtype="float32")

    def __init__(self, voice_id: str | None = None, model_id: str | None = None):
        cfg = load_config()
        self.voice_id = voice_id or cfg.cartesia_voice_id
        self.model_id = model_id or cfg.cartesia_model_id
        self.client = AsyncCartesia(api_key=cfg.cartesia_api_key)

    async def generate_speech(self, text: str) -> bytes:
        """Synthesize text into speech and return full WAV audio bytes."""
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
        """Stream text chunks to Cartesia via WebSocket and yield synthesised audio chunks concurrently."""
        async with self.client.tts.websocket_connect() as connection:
            ctx = connection.context(
                model_id=self.model_id,
                voice={"mode": "id", "id": self.voice_id},
                output_format={"container": "raw", "sample_rate": 44100, "encoding": "pcm_f32le"},
            )

            async def sender():
                async for chunk in text_stream:
                    await ctx.send(
                        transcript=chunk,
                        voice={"mode": "id", "id": self.voice_id},
                        continue_=True,
                    )
                await ctx.no_more_inputs()

            async def receiver():
                async for output in ctx.receive():
                    if output.type == "chunk":
                        yield output.audio
                    elif output.type == "error":
                        raise RuntimeError(f"Cartesia WebSocket error: {output.message}")

            send_task = asyncio.create_task(sender())
            try:
                async for audio_chunk in receiver():
                    yield audio_chunk
            finally:
                await send_task

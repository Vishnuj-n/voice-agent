import io
import os
from groq import AsyncGroq
from pydantic_ai.models import Model
from pydantic_ai.models.groq import GroqModel

from config import load_config
from providers.base import LLMProvider, STTProvider


class GroqWhisperSTT(STTProvider):
    """Groq Speech-to-Text provider utilizing the official Groq SDK."""

    def __init__(self, model: str | None = None):
        cfg = load_config()
        self.model = model or cfg.groq_stt_model

        # Ensure environment variable is set for Groq client
        if cfg.groq_api_key:
            os.environ["GROQ_API_KEY"] = cfg.groq_api_key

        # Official client used for STT direct calls
        self.client = AsyncGroq(api_key=cfg.groq_api_key)

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


import asyncio
import wave
import numpy as np
from typing import AsyncIterator
from providers.base import StreamingSTTProvider, STTResult


class GroqStreamingWhisperSTT(StreamingSTTProvider):
    """Sliding-window streaming STT provider using Groq Whisper.

    Allows streaming interim transcripts using standard Groq API keys:
    - Buffers incoming PCM audio.
    - Runs periodic fast Whisper transcriptions during active speech.
    - Emits interim results ('hello' -> 'hello how' ...).
    - Detects silence end-of-speech and emits speech_final result.
    """

    def __init__(
        self,
        model: str | None = None,
        sample_rate: int = 16000,
        silence_threshold: float = 200.0,
        silence_duration: float = 1.0,
        min_speech_duration: float = 0.3,
    ):
        cfg = load_config()
        self.model = model or cfg.groq_stt_model
        self.sample_rate = sample_rate
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.min_speech_duration = min_speech_duration

        self.client = AsyncGroq(api_key=cfg.groq_api_key)
        self._audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._results_queue: asyncio.Queue[STTResult | None] = asyncio.Queue()
        self._processor_task: asyncio.Task | None = None
        self._closed = False

    async def connect(self) -> None:
        self._closed = False
        self._processor_task = asyncio.create_task(self._process_stream())

    async def send_audio(self, audio_chunk: bytes) -> None:
        if not self._closed:
            await self._audio_queue.put(audio_chunk)

    async def _process_stream(self) -> None:
        """Continuously process audio chunks with energy VAD and sliding Whisper calls."""
        window_bytes = self.sample_rate * 2 // 10  # 0.1s chunk
        silence_limit = int(self.silence_duration / 0.1)
        min_speech_chunks = int(self.min_speech_duration / 0.1)

        accumulated_pcm = bytearray()
        partial = bytearray()
        speech_started = False
        consecutive_silence = 0
        speech_chunks = 0
        last_transcribe_chunks = 0

        try:
            while not self._closed:
                try:
                    chunk = await asyncio.wait_for(self._audio_queue.get(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue

                if chunk is None:
                    break

                partial.extend(chunk)

                while len(partial) >= window_bytes:
                    window = bytes(partial[:window_bytes])
                    partial = partial[window_bytes:]

                    samples = np.frombuffer(window, dtype=np.int16).astype(np.float32)
                    rms = float(np.sqrt(np.mean(samples**2)))

                    if not speech_started:
                        if rms > self.silence_threshold:
                            speech_started = True
                            accumulated_pcm.extend(window)
                            speech_chunks = 1
                            consecutive_silence = 0
                    else:
                        accumulated_pcm.extend(window)
                        if rms >= self.silence_threshold:
                            speech_chunks += 1
                            consecutive_silence = 0
                        else:
                            consecutive_silence += 1

                        # Periodic interim transcription every ~0.4s during speech
                        if speech_chunks >= min_speech_chunks and (speech_chunks - last_transcribe_chunks) >= 4:
                            last_transcribe_chunks = speech_chunks
                            asyncio.create_task(self._transcribe_interim(bytes(accumulated_pcm)))

                        # End of speech detection
                        if consecutive_silence >= silence_limit:
                            if speech_chunks >= min_speech_chunks:
                                wav_data = self._wrap_wav(bytes(accumulated_pcm))
                                final_text = await self._run_whisper(wav_data)
                                if final_text:
                                    await self._results_queue.put(
                                        STTResult(text=final_text, is_final=True, is_speech_final=True)
                                    )
                            accumulated_pcm.clear()
                            speech_started = False
                            consecutive_silence = 0
                            speech_chunks = 0
                            last_transcribe_chunks = 0

        except asyncio.CancelledError:
            pass
        finally:
            await self._results_queue.put(None)

    async def _transcribe_interim(self, pcm_data: bytes) -> None:
        """Run quick interim transcription without blocking."""
        try:
            wav_data = self._wrap_wav(pcm_data)
            text = await self._run_whisper(wav_data)
            if text and not self._closed:
                await self._results_queue.put(
                    STTResult(text=text, is_final=False, is_speech_final=False)
                )
        except Exception:
            pass

    async def _run_whisper(self, wav_bytes: bytes) -> str:
        bio = io.BytesIO(wav_bytes)
        bio.name = "audio.wav"
        resp = await self.client.audio.transcriptions.create(
            file=bio,
            model=self.model,
            response_format="json",
            language="en",
        )
        return resp.text.strip()

    def _wrap_wav(self, pcm_data: bytes) -> bytes:
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(pcm_data)
        return wav_buf.getvalue()

    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio bytes directly."""
        return await self._run_whisper(audio_data)

    async def stream_transcripts(self) -> AsyncIterator[STTResult]:
        while True:
            res = await self._results_queue.get()
            if res is None:
                break
            yield res

    async def close(self) -> None:
        self._closed = True
        if self._processor_task and not self._processor_task.done():
            self._processor_task.cancel()


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

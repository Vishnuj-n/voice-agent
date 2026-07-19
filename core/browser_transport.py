import asyncio
import base64
import io
import wave
import numpy as np
from typing import AsyncIterator

from providers.base import Transport, AudioFormat


class BrowserTransport(Transport):
    """Transport that bridges the StreamingPipeline to a WebSocket.

    Receives base64-encoded PCM Int16 chunks from the browser into an async
    buffer. read_audio() applies energy-based VAD to detect utterance
    boundaries — it collects audio until silence is detected, then returns
    a complete WAV suitable for STT. This mirrors LocalTransport.read_audio()
    so the pipeline works identically for both transports.
    """

    def __init__(
        self,
        silence_threshold: float = 200.0,
        silence_duration: float = 2.0,
        max_duration: float = 30.0,
        min_speech_duration: float = 0.3,
        warmup_duration: float = 1.5,
        sample_rate: int = 16000,
    ):
        self._ws = None
        self._audio_buffer: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._audio_format: AudioFormat | None = None
        self._silence_threshold = silence_threshold
        self._silence_duration = silence_duration
        self._max_duration = max_duration
        self._min_speech_duration = min_speech_duration
        self._warmup_duration = warmup_duration
        self._sample_rate = sample_rate

    def set_websocket(self, ws) -> None:
        """Set the WebSocket connection for this transport."""
        self._ws = ws

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        """Clear the WebSocket reference and drain the buffer."""
        self._ws = None
        # Unblock any pending read_audio by pushing a sentinel
        try:
            self._audio_buffer.put_nowait(None)
        except asyncio.QueueFull:
            pass

    async def feed_audio(self, audio_bytes: bytes) -> None:
        """Feed raw PCM Int16 bytes from the browser into the transport buffer."""
        await self._audio_buffer.put(audio_bytes)

    async def read_audio(self) -> bytes:
        """Read audio from the browser and return a complete WAV utterance.

        Applies energy-based VAD to detect speech start and silence end,
        mirroring LocalTransport._record() behavior. Returns a WAV blob
        suitable for STT, or empty bytes if no speech was detected.
        """
        chunks: list[bytes] = []
        speech_started = False
        consecutive_silence = 0
        speech_chunks = 0  # Track actual speech windows

        # VAD parameters — match CLI thresholds
        # Process in ~0.1s windows at 16kHz = 1600 samples = 3200 bytes (Int16)
        window_bytes = self._sample_rate * 2 // 10  # 0.1s of Int16 mono
        silence_chunks_limit = int(self._silence_duration / 0.1)
        warmup_chunks_limit = int(self._warmup_duration / 0.1)
        max_chunks = int(self._max_duration / 0.1)
        min_speech_chunks = int(self._min_speech_duration / 0.1)

        partial = b""
        chunk_count = 0

        try:
            while chunk_count < max_chunks:
                raw = await asyncio.wait_for(self._audio_buffer.get(), timeout=1.0)
                if raw is None or len(raw) == 0:
                    break

                partial += raw

                # Process complete windows for VAD
                while len(partial) >= window_bytes:
                    window = partial[:window_bytes]
                    partial = partial[window_bytes:]
                    chunk_count += 1

                    # Compute RMS energy over the Int16 window
                    samples = np.frombuffer(window, dtype=np.int16).astype(np.float32)
                    rms = float(np.sqrt(np.mean(samples**2)))

                    if not speech_started:
                        if rms > self._silence_threshold:
                            speech_started = True
                            chunks.append(window)
                            speech_chunks = 1
                        elif chunk_count >= warmup_chunks_limit:
                            # No speech in warmup window
                            return b""
                    else:
                        chunks.append(window)
                        if rms >= self._silence_threshold:
                            speech_chunks += 1

                        if rms < self._silence_threshold:
                            consecutive_silence += 1
                        else:
                            consecutive_silence = 0

                        if consecutive_silence >= silence_chunks_limit:
                            # Reject utterances shorter than minimum — likely noise
                            if speech_chunks < min_speech_chunks:
                                chunks.clear()
                                speech_started = False
                                consecutive_silence = 0
                                speech_chunks = 0
                                continue

                            # Flush any remaining partial buffer as a trailing chunk
                            if partial:
                                samples_p = np.frombuffer(
                                    partial, dtype=np.int16
                                ).astype(np.float32)
                                rms_p = float(np.sqrt(np.mean(samples_p**2)))
                                if rms_p >= self._silence_threshold * 0.5:
                                    chunks.append(partial)
                            return self._wrap_wav(b"".join(chunks))

        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass

        if not speech_started or not chunks:
            return b""

        # Stream ended (WS closed or max duration) — return what we have
        if partial:
            chunks.append(partial)
        return self._wrap_wav(b"".join(chunks))

    def _wrap_wav(self, pcm_data: bytes) -> bytes:
        """Wrap raw PCM Int16 mono data in a WAV container."""
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # Int16 = 2 bytes
            wav_file.setframerate(self._sample_rate)
            wav_file.writeframes(pcm_data)
        return wav_buf.getvalue()

    async def write_audio(self, audio_data: bytes) -> bool:
        """Write complete audio to browser (unused in streaming mode)."""
        return True

    async def play_stream(
        self,
        audio_chunks: AsyncIterator[bytes],
        audio_format: AudioFormat,
    ) -> None:
        """Stream raw PCM chunks to the browser over WebSocket.

        Called by StreamingPipeline. Sends each chunk as a base64-encoded
        binary message to the connected WebSocket client.
        """
        self._audio_format = audio_format

        # Send audio_start header
        if self._ws:
            await self._ws.send_json(
                {
                    "type": "audio_start",
                    "format": {
                        "sample_rate": audio_format.sample_rate,
                        "channels": audio_format.num_channels,
                        "encoding": audio_format.dtype,
                    },
                }
            )

        # Stream audio chunks
        async for chunk in audio_chunks:
            if self._ws:
                encoded = base64.b64encode(chunk).decode("ascii")
                await self._ws.send_json(
                    {
                        "type": "audio_chunk",
                        "data": encoded,
                    }
                )

        # Signal end of audio stream
        if self._ws:
            await self._ws.send_json({"type": "audio_end"})

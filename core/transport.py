import io
import wave
import asyncio
from typing import AsyncIterator
import numpy as np
import sounddevice as sd
from providers.base import Transport, AudioFormat


class LocalTransport(Transport):
    def __init__(
        self,
        silence_threshold: float = 300.0,
        silence_duration: float = 1.5,
        max_duration: float = 10.0,
        samplerate: int = 16000,
    ):
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.max_duration = max_duration
        self.samplerate = samplerate

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def read_audio(self) -> bytes:
        return await asyncio.to_thread(self._record)

    def _record(self) -> bytes:
        chunk_size = 1600  # 0.1 seconds at 16000 Hz
        recorded_chunks = []

        with sd.InputStream(
            samplerate=self.samplerate, channels=1, dtype="int16"
        ) as stream:
            print("  [mic] Recording... Speak now.")
            consecutive_silence_chunks = 0
            silence_chunks_limit = int(
                self.silence_duration / (chunk_size / self.samplerate)
            )
            max_chunks = int(self.max_duration / (chunk_size / self.samplerate))

            speech_started = False
            chunks_recorded = 0

            while chunks_recorded < max_chunks:
                data, overflowed = stream.read(chunk_size)
                recorded_chunks.append(data)
                chunks_recorded += 1

                # Compute RMS energy
                rms = np.sqrt(np.mean(data.astype(np.float32) ** 2))

                if not speech_started:
                    if rms > self.silence_threshold:
                        speech_started = True
                        print("  [mic] Speech detected...")
                    else:
                        # Allow up to 3 seconds of silence at start
                        if chunks_recorded >= int(3.0 / (chunk_size / self.samplerate)):
                            print("  [mic] No speech detected, stopping.")
                            break
                else:
                    if rms < self.silence_threshold:
                        consecutive_silence_chunks += 1
                    else:
                        consecutive_silence_chunks = 0

                    if consecutive_silence_chunks >= silence_chunks_limit:
                        print("  [mic] Silence detected, stopping.")
                        break

            print("  [mic] Recording stopped.")

        audio_data = np.concatenate(recorded_chunks, axis=0)
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.samplerate)
            wav_file.writeframes(audio_data.tobytes())

        return wav_buf.getvalue()

    async def play_stream(
        self,
        audio_chunks: AsyncIterator[bytes],
        audio_format: AudioFormat,
    ) -> None:
        """Stream raw PCM chunks to the speaker as they arrive.

        Opens a RawOutputStream and writes each chunk immediately,
        so audio playback begins as soon as the first chunk is available.
        Blocks (awaits) until the stream is exhausted.
        """
        with sd.RawOutputStream(
            samplerate=audio_format.sample_rate,
            channels=audio_format.num_channels,
            dtype=audio_format.dtype,
        ) as stream:
            async for chunk in audio_chunks:
                await asyncio.to_thread(stream.write, chunk)

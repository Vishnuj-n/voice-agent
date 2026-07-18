import io
import wave
import asyncio
from typing import AsyncIterator
import numpy as np
import sounddevice as sd
from providers.base import Transport, AudioFormat

class LocalTransport(Transport):
    def __init__(self, silence_threshold: float = 300.0, silence_duration: float = 1.5, max_duration: float = 10.0, samplerate: int = 16000):
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
        
        with sd.InputStream(samplerate=self.samplerate, channels=1, dtype='int16') as stream:
            print("  [mic] Recording... Speak now.")
            consecutive_silence_chunks = 0
            silence_chunks_limit = int(self.silence_duration / (chunk_size / self.samplerate))
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
        with wave.open(wav_buf, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.samplerate)
            wav_file.writeframes(audio_data.tobytes())
            
        return wav_buf.getvalue()

    async def write_audio(self, audio_data: bytes) -> bool:
        return await asyncio.to_thread(self._play, audio_data)

    def _play(self, audio_data: bytes) -> bool:
        try:
            # Parse WAV header manually to support both PCM and IEEE float formats.
            # Python's wave module only supports format 1 (PCM) and rejects
            # format 3 (IEEE float) used by Cartesia's pcm_f32le output.
            if audio_data[:4] != b'RIFF' or audio_data[8:12] != b'WAVE':
                raise ValueError("Not a WAV file")

            fmt_tag = audio_data[20:22]
            channels = int.from_bytes(audio_data[22:24], 'little')
            frame_rate = int.from_bytes(audio_data[24:28], 'little')
            bits_per_sample = int.from_bytes(audio_data[34:36], 'little')

            # Find the 'data' chunk
            data_offset = 12
            while data_offset < len(audio_data) - 8:
                chunk_id = audio_data[data_offset:data_offset + 4]
                chunk_size = int.from_bytes(audio_data[data_offset + 4:data_offset + 8], 'little')
                if chunk_id == b'data':
                    data_offset += 8
                    break
                data_offset += 8 + chunk_size
            else:
                raise ValueError("No data chunk found in WAV file")

            raw_data = audio_data[data_offset:data_offset + chunk_size]

            if fmt_tag == b'\x03\x00' and bits_per_sample == 32:
                # IEEE float 32-bit (format tag 3) — Cartesia pcm_f32le output
                data = np.frombuffer(raw_data, dtype=np.float32)
            elif fmt_tag == b'\x01\x00' and bits_per_sample == 16:
                data = np.frombuffer(raw_data, dtype=np.int16)
            elif fmt_tag == b'\x01\x00' and bits_per_sample == 8:
                data = np.frombuffer(raw_data, dtype=np.uint8).astype(np.float32) - 128
            elif fmt_tag == b'\x01\x00' and bits_per_sample == 32:
                data = np.frombuffer(raw_data, dtype=np.int32).astype(np.float32)
            else:
                raise ValueError(f"Unsupported WAV format: tag={fmt_tag.hex()}, bits={bits_per_sample}")

            if channels > 1:
                data = data.reshape(-1, channels)

            sd.play(data, samplerate=frame_rate)
            sd.wait()
            return True
        except Exception as e:
            print(f"Error in playback: {e}")
            return False

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

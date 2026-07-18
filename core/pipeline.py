import asyncio
import time
import dataclasses
from typing import AsyncIterator

@dataclasses.dataclass
class TextChunker:
    """Heuristic sentence/clause chunker for LLM streaming deltas.

    Buffers tiny deltas and flushes when a sentence boundary (`.`, `!`, `?`),
    clause boundary (`,`, `;`, `:`), or the max buffer length is reached.
    Remaining buffered text is always flushed when streaming ends via flush().
    """
    _max_buffer: int = 200
    _buffer: str = ""

    def feed(self, delta: str) -> str | None:
        """Accumulate a delta. Returns a chunk when a flush boundary is hit, else None."""
        self._buffer += delta

        # 1. Sentence boundaries — always flush
        for sep in (". ", "! ", "? ", ".\n", "!\n", "?\n"):
            idx = self._buffer.rfind(sep)
            if idx != -1:
                chunk = self._buffer[: idx + len(sep)].strip()
                self._buffer = self._buffer[idx + len(sep) :]
                return chunk if chunk else None

        # 2. Clause boundaries — flush only when buffer exceeds half the max
        if len(self._buffer) > self._max_buffer // 2:
            for sep in (", ", "; ", ": ", ",\n", ";\n", ":\n"):
                idx = self._buffer.rfind(sep)
                if idx != -1:
                    chunk = self._buffer[: idx + len(sep)].strip()
                    self._buffer = self._buffer[idx + len(sep) :]
                    return chunk if chunk else None

        # 3. Max buffer length — hard flush
        if len(self._buffer) >= self._max_buffer:
            chunk = self._buffer.strip()
            self._buffer = ""
            return chunk if chunk else None

        return None

    def flush(self) -> str | None:
        """Flush any remaining buffered content. Called when the LLM stream ends."""
        chunk = self._buffer.strip()
        self._buffer = ""
        return chunk


@dataclasses.dataclass
class TurnResult:
    """Result of a single streaming turn."""
    full_text: str
    llm_total_ms: float
    llm_time_to_first_token_ms: float
    tts_time_to_first_audio_ms: float
    total_ms: float


class StreamingPipeline:
    def __init__(self, bot_agent, transport, tts):
        self._agent = bot_agent
        self._transport = transport
        self._tts = tts

    async def run_turn(self, user_text: str) -> TurnResult:
        t0 = time.perf_counter()
        t_first_token = None
        t_first_audio = None
        t_llm_done = None

        # 1. Open the PydanticAI streaming response
        async with self._agent.run_stream(user_text) as response:
            # Internal queues (NOT exposed publicly)
            text_queue: asyncio.Queue[str | None] = asyncio.Queue()
            audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

            # 2. LLM producer: stream_text → text_queue
            async def llm_producer():
                nonlocal t_first_token, t_llm_done
                async for token in response.stream_text(delta=True):
                    if t_first_token is None:
                        t_first_token = time.perf_counter()
                    await text_queue.put(token)
                t_llm_done = time.perf_counter()
                await text_queue.put(None)  # sentinel

            # 3. TTS bridge: text_queue → TextChunker → TTSProvider → audio_queue
            async def tts_bridge():
                nonlocal t_first_audio
                chunker = TextChunker()

                async def text_gen():
                    while True:
                        item = await text_queue.get()
                        if item is None:
                            remaining = chunker.flush()
                            if remaining:
                                yield remaining
                            break
                        chunk = chunker.feed(item)
                        if chunk:
                            yield chunk

                async for audio_bytes in self._tts.generate_speech_stream(text_gen()):
                    if t_first_audio is None:
                        t_first_audio = time.perf_counter()
                    await audio_queue.put(audio_bytes)
                await audio_queue.put(None)  # sentinel

            # 4. Audio frame generator: audio_queue → AsyncIterator[bytes]
            async def audio_frame_gen():
                while True:
                    frame = await audio_queue.get()
                    if frame is None:
                        break
                    yield frame

            # 5. Run all three concurrently — playback starts as soon as the
            #    first audio chunk arrives, while the LLM is still generating.
            await asyncio.gather(
                llm_producer(),
                tts_bridge(),
                self._transport.play_stream(audio_frame_gen(), self._tts.audio_format),
            )

            # 6. Collect full text (inside async with — response is still valid)
            full_text = await response.get_output()

        t_end = time.perf_counter()

        # 7. Compute timing
        llm_total_ms = ((t_llm_done - t0) * 1000) if t_llm_done else 0.0
        llm_time_to_first_token_ms = (
            (t_first_token - t0) * 1000 if t_first_token else 0.0
        )
        tts_time_to_first_audio_ms = (
            (t_first_audio - t0) * 1000 if t_first_audio else 0.0
        )
        total_ms = (t_end - t0) * 1000

        return TurnResult(
            full_text=full_text,
            llm_total_ms=llm_total_ms,
            llm_time_to_first_token_ms=llm_time_to_first_token_ms,
            tts_time_to_first_audio_ms=tts_time_to_first_audio_ms,
            total_ms=total_ms,
        )

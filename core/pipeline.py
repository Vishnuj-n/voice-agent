import asyncio
import time
import dataclasses
from typing import AsyncIterator, Callable, Awaitable


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
    stt_ms: float
    llm_total_ms: float
    llm_time_to_first_token_ms: float
    tts_total_ms: float
    tts_time_to_first_audio_ms: float
    total_ms: float


@dataclasses.dataclass
class PipelineCallbacks:
    """Optional streaming event hooks for the pipeline.

    All fields default to None. The pipeline only fires callbacks that are set.
    CLI callers pass no callbacks; the web layer provides them for WebSocket forwarding.
    """
    on_transcript: Callable[[str], Awaitable[None]] | None = None
    on_text_delta: Callable[[str], Awaitable[None]] | None = None
    on_status: Callable[[str], Awaitable[None]] | None = None
    on_complete: Callable[[str], Awaitable[None]] | None = None


class StreamingPipeline:
    def __init__(self, bot_agent, transport, tts, stt):
        """Create a StreamingPipeline.

        Args:
            bot_agent: PydanticAI agent that drives the LLM.
            transport:  Transport implementation (LocalTransport or BrowserTransport).
            tts:        TTSProvider — converts text chunks to audio.
            stt:        STTProvider — transcribes audio to text (required).
        """
        self._agent = bot_agent
        self._transport = transport
        self._tts = tts
        self._stt = stt
        self._cancel_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def cancel(self) -> None:
        """Signal cancellation of the current turn.

        Stops LLM streaming, TTS generation, audio playback, and pending
        callback tasks. Safe to call from any coroutine or task.
        """
        self._cancel_event.set()

    def reset_cancel(self) -> None:
        """Clear the cancellation signal before starting a new turn."""
        self._cancel_event.clear()

    async def run_text_turn(
        self,
        text: str,
        callbacks: PipelineCallbacks | None = None,
    ) -> TurnResult:
        """Run a single streaming turn from pre-transcribed text (CLI path).

        Skips STT entirely — the caller is responsible for transcription.
        """
        return await self._run_turn(text=text, callbacks=callbacks)

    async def run_audio_turn(
        self,
        audio: bytes,
        callbacks: PipelineCallbacks | None = None,
    ) -> TurnResult:
        """Run a single streaming turn from raw audio bytes (browser path).

        STT is run first to produce the transcript, then the LLM + TTS pipeline
        executes exactly as in run_text_turn.
        """
        return await self._run_turn(audio=audio, callbacks=callbacks)

    # ------------------------------------------------------------------
    # Private implementation
    # ------------------------------------------------------------------

    async def _run_turn(
        self,
        text: str | None = None,
        audio: bytes | None = None,
        callbacks: PipelineCallbacks | None = None,
    ) -> TurnResult:
        """Core turn implementation shared by run_text_turn and run_audio_turn.

        Exactly one of ``text`` or ``audio`` must be provided.
        When ``callbacks`` is supplied the pipeline fires streaming events so
        the caller can forward them (e.g. over WebSocket).
        """
        self.reset_cancel()
        cb = callbacks or PipelineCallbacks()
        t0 = time.perf_counter()
        t_first_token = None
        t_first_audio = None
        t_llm_done = None
        stt_ms = 0.0
        tts_done_ms = 0.0
        tracked_tasks: list[asyncio.Task] = []

        def _track_callback(coro):
            """Wrap a callback coroutine in a tracked fire-and-forget task.

            Exceptions are logged instead of being silently lost.
            """
            task = asyncio.create_task(coro)
            tracked_tasks.append(task)
            task.add_done_callback(_log_task_exception)
            return task

        def _log_task_exception(task: asyncio.Task):
            if task.cancelled():
                return
            exc = task.exception()
            if exc is not None:
                import logging
                logging.getLogger("voice-agent").error(
                    f"Callback task error: {exc}", exc_info=exc
                )

        # 1. STT — only when audio bytes are provided
        if audio is not None:
            if cb.on_status:
                await cb.on_status("thinking")
            t_stt_start = time.perf_counter()
            text = await self._stt.transcribe(audio)
            stt_ms = (time.perf_counter() - t_stt_start) * 1000
            if cb.on_transcript:
                _track_callback(cb.on_transcript(text))

        if self._cancel_event.is_set():
            return TurnResult(
                full_text="", stt_ms=stt_ms, llm_total_ms=0.0,
                llm_time_to_first_token_ms=0.0, tts_total_ms=0.0,
                tts_time_to_first_audio_ms=0.0, total_ms=(time.perf_counter() - t0) * 1000,
            )

        # 2. Open the PydanticAI streaming response
        async with self._agent.run_stream(text) as response:
            text_queue: asyncio.Queue[str | None] = asyncio.Queue()
            audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

            # 3. LLM producer: stream_text → text_queue
            async def llm_producer():
                nonlocal t_first_token, t_llm_done
                async for token in response.stream_text(delta=True):
                    if self._cancel_event.is_set():
                        break
                    if t_first_token is None:
                        t_first_token = time.perf_counter()
                    await text_queue.put(token)
                    if cb.on_text_delta:
                        _track_callback(cb.on_text_delta(token))
                t_llm_done = time.perf_counter()
                await text_queue.put(None)  # sentinel

            # 4. TTS bridge: text_queue → TextChunker → TTSProvider → audio_queue
            async def tts_bridge():
                nonlocal t_first_audio, tts_done_ms
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

                try:
                    async for audio_bytes in self._tts.generate_speech_stream(text_gen()):
                        if self._cancel_event.is_set():
                            break
                        if t_first_audio is None:
                            t_first_audio = time.perf_counter()
                            if cb.on_status:
                                await cb.on_status("speaking")
                        await audio_queue.put(audio_bytes)
                finally:
                    tts_done_ms = (time.perf_counter() - t0) * 1000
                    await audio_queue.put(None)  # sentinel

            # 5. Audio frame generator: audio_queue → AsyncIterator[bytes]
            async def audio_frame_gen():
                while True:
                    frame = await audio_queue.get()
                    if frame is None:
                        break
                    yield frame

            # 6. Run all three concurrently — playback starts as soon as the
            #    first audio chunk arrives, while the LLM is still generating.
            await asyncio.gather(
                llm_producer(),
                tts_bridge(),
                self._transport.play_stream(audio_frame_gen(), self._tts.audio_format),
            )

            # 7. Wait for any outstanding callback tasks before collecting output
            if tracked_tasks:
                await asyncio.gather(*tracked_tasks, return_exceptions=True)

            # 8. Collect full text (inside async with — response is still valid)
            full_text = await response.get_output()

        t_end = time.perf_counter()

        # 9. Compute timing — STT is already measured independently above
        llm_total_ms = ((t_llm_done - t0) * 1000) if t_llm_done else 0.0
        # LLM time excludes STT: measure from when LLM started (after STT)
        if t_first_token is not None and audio is not None:
            llm_time_to_first_token_ms = (t_first_token - (t0 + stt_ms / 1000)) * 1000
        else:
            llm_time_to_first_token_ms = (
                (t_first_token - t0) * 1000 if t_first_token else 0.0
            )
        tts_total_ms = tts_done_ms if tts_done_ms else 0.0
        tts_time_to_first_audio_ms = (
            (t_first_audio - t0) * 1000 if t_first_audio else 0.0
        )
        total_ms = (t_end - t0) * 1000

        # 10. Fire on_complete with the full assistant response
        if cb.on_complete:
            await cb.on_complete(full_text)

        return TurnResult(
            full_text=full_text,
            stt_ms=stt_ms,
            llm_total_ms=llm_total_ms,
            llm_time_to_first_token_ms=llm_time_to_first_token_ms,
            tts_total_ms=tts_total_ms,
            tts_time_to_first_audio_ms=tts_time_to_first_audio_ms,
            total_ms=total_ms,
        )

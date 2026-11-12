import asyncio
import json
import logging
from typing import AsyncIterator
import websockets

from config import load_config
from providers.base import StreamingSTTProvider, STTResult

logger = logging.getLogger("voice-agent")


class DeepgramLiveSTT(StreamingSTTProvider):
    """Real-time Streaming Speech-to-Text provider using Deepgram's WebSocket API."""

    def __init__(
        self,
        model: str | None = None,
        sample_rate: int = 16000,
        endpointing_ms: int = 400,
        interim_results: bool = True,
    ):
        cfg = load_config()
        self.api_key = cfg.deepgram_api_key
        self.model = model or cfg.deepgram_stt_model
        self.sample_rate = sample_rate
        self.endpointing_ms = endpointing_ms
        self.interim_results = interim_results
        self._ws = None
        self._results_queue: asyncio.Queue[STTResult | None] = asyncio.Queue()
        self._receive_task: asyncio.Task | None = None
        self._closed = False

    async def connect(self) -> None:
        """Connect to Deepgram's streaming websocket."""
        if not self.api_key:
            raise ValueError("DEEPGRAM_API_KEY is not configured in settings or environment.")

        # Deepgram Live WebSocket URL with query parameters
        url = (
            f"wss://api.deepgram.com/v1/listen?"
            f"model={self.model}&"
            f"encoding=linear16&"
            f"sample_rate={self.sample_rate}&"
            f"channels=1&"
            f"punctuate=true&"
            f"interim_results={'true' if self.interim_results else 'false'}&"
            f"endpointing={self.endpointing_ms}&"
            f"vad_events=true"
        )
        headers = {"Authorization": f"Token {self.api_key}"}

        self._ws = await websockets.connect(url, additional_headers=headers)
        self._closed = False
        self._receive_task = asyncio.create_task(self._listen_loop())
        logger.info("Connected to Deepgram Live STT")

    async def _listen_loop(self) -> None:
        """Receive JSON messages from Deepgram and push parsed STTResult to queue."""
        try:
            async for raw_msg in self._ws:
                msg = json.loads(raw_msg)
                msg_type = msg.get("type")

                if msg_type == "Results":
                    channel = msg.get("channel", {})
                    alternatives = channel.get("alternatives", [])
                    if not alternatives:
                        continue

                    transcript = alternatives[0].get("transcript", "")
                    is_final = msg.get("is_final", False)
                    speech_final = msg.get("speech_final", False)

                    if transcript:
                        await self._results_queue.put(
                            STTResult(
                                text=transcript,
                                is_final=is_final,
                                is_speech_final=speech_final,
                            )
                        )
                elif msg_type == "UtteranceEnd":
                    # Deepgram UtteranceEnd event
                    await self._results_queue.put(
                        STTResult(text="", is_final=True, is_speech_final=True)
                    )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Deepgram websocket receive error: {e}", exc_info=True)
        finally:
            await self._results_queue.put(None)

    async def send_audio(self, audio_chunk: bytes) -> None:
        """Send raw PCM Int16 audio chunk directly to Deepgram."""
        if self._ws and not self._closed:
            try:
                await self._ws.send(audio_chunk)
            except Exception as e:
                logger.warning(f"Failed to send audio to Deepgram: {e}")

    async def stream_transcripts(self) -> AsyncIterator[STTResult]:
        """Stream parsed transcript events from the internal queue."""
        while True:
            result = await self._results_queue.get()
            if result is None:
                break
            yield result

    async def transcribe(self, audio_data: bytes) -> str:
        """Batch fallback transcribe using connection lifecycle."""
        await self.connect()
        await self.send_audio(audio_data)
        # Send close frame
        await self._ws.send(json.dumps({"type": "CloseStream"}))

        full_text = []
        async for res in self.stream_transcripts():
            if res.is_final and res.text:
                full_text.append(res.text)

        await self.close()
        return " ".join(full_text).strip()

    async def close(self) -> None:
        """Close WebSocket session and stop receiving."""
        self._closed = True
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
        if self._ws:
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

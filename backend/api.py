import asyncio
import base64
import json
import logging
import re
import sys
import uuid
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("voice-agent")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.browser_transport import BrowserTransport
from core.pipeline import StreamingPipeline, PipelineCallbacks
from providers.registry import get_stt_provider, get_tts_provider
from bots import BOT_REGISTRY
from config import load_config
from db.session import record_session_start, record_session_end, record_turn

app = FastAPI(title="Voice Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[load_config().web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BOTS = [
    {"id": "healthcare", "name": "Healthcare", "enabled": True},
    {"id": "travel", "name": "Travel", "enabled": True},
    {"id": "finance", "name": "Finance", "enabled": True},
    {"id": "legal", "name": "Legal", "enabled": True},
]



@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    logger.info("WebSocket connection attempt")
    await ws.accept()
    logger.info("WebSocket accepted")

    transport = BrowserTransport()
    transport.set_websocket(ws)

    try:
        stt = get_stt_provider()
        tts = get_tts_provider()
    except Exception as e:
        logger.error(f"Provider init failed: {e}")
        await ws.send_json({"type": "error", "message": f"Provider init failed: {e}"})
        await ws.close()
        return

    cfg = load_config()
    default_bot = cfg.default_bot
    default_agent = BOT_REGISTRY.get(default_bot, BOT_REGISTRY["healthcare"])

    pipeline = StreamingPipeline(
        bot_agent=default_agent,
        transport=transport,
        tts=tts,
        stt=stt,
    )

    current_bot = default_bot
    conversation_task: asyncio.Task | None = None
    session_active = False
    current_session_id: str | None = None
    turn_counter = 0

    await ws.send_json({"type": "status", "state": "connected"})
    await ws.send_json({"type": "bots", "bots": BOTS})
    await ws.send_json({"type": "bot_selected", "bot": current_bot})
    logger.info(f"Sent initial status, bots list, and active bot: {current_bot}")

    async def streaming_stt_loop():
        """Streaming STT session loop.

        Pipes live audio chunks directly into the streaming STT provider,
        forwards interim transcripts ('hello' -> 'hello how' ...) to the UI,
        and triggers the LLM turn as soon as endpointing / end-of-speech occurs.
        """
        nonlocal session_active
        session_active = True
        logger.info("Streaming STT conversation loop started")

        try:
            await stt.connect()

            accumulated_transcript = ""

            async def feed_audio_loop():
                while session_active and not pipeline._cancel_event.is_set():
                    try:
                        chunk = await transport._audio_buffer.get()
                        if chunk is None:
                            break
                        await stt.send_audio(chunk)
                    except (asyncio.CancelledError, Exception):
                        break

            audio_feeder = asyncio.create_task(feed_audio_loop())

            async for result in stt.stream_transcripts():
                if not session_active or pipeline._cancel_event.is_set():
                    break

                if result.text:
                    accumulated_transcript = result.text.strip()
                    # Send live interim transcript to frontend only while utterance is in progress
                    if not result.is_final:
                        await ws.send_json(
                            {
                                "type": "interim_transcript",
                                "text": accumulated_transcript,
                                "speaker": "user",
                                "is_final": False,
                            }
                        )

                # When Deepgram / STT detects end of speech (endpointing)
                if result.is_speech_final and accumulated_transcript:
                    final_text = accumulated_transcript.strip()
                    accumulated_transcript = ""

                    # Filter out Whisper silence/punctuation hallucinations (e.g. '.', '...', ' !')
                    clean_text = re.sub(r"[^\w\s]", "", final_text).strip()
                    if not clean_text:
                        logger.info(f"Ignored noise/punctuation-only transcript: '{final_text}'")
                        continue

                    logger.info(f"End of speech detected: '{final_text}' -> Triggering LLM")

                    # Broadcast final confirmed transcript strictly once
                    await ws.send_json(
                        {
                            "type": "transcript",
                            "text": final_text,
                            "speaker": "user",
                            "is_final": True,
                        }
                    )

                    callbacks = PipelineCallbacks(
                        on_text_delta=lambda token: ws.send_json(
                            {
                                "type": "response_text",
                                "text": token,
                            }
                        ),
                        on_status=lambda state: ws.send_json(
                            {
                                "type": "status",
                                "state": state,
                            }
                        ),
                    )

                    try:
                        result_turn = await pipeline.run_text_turn(
                            text=final_text, callbacks=callbacks
                        )
                        logger.info(f"Pipeline turn complete: total={round(result_turn.total_ms)}ms")

                        await ws.send_json(
                            {
                                "type": "metrics",
                                "stt_ms": round(result_turn.stt_ms),
                                "llm_total_ms": round(result_turn.llm_total_ms),
                                "llm_time_to_first_token_ms": round(
                                    result_turn.llm_time_to_first_token_ms
                                ),
                                "tts_time_to_first_audio_ms": round(
                                    result_turn.tts_time_to_first_audio_ms
                                ),
                                "tts_total_ms": round(result_turn.tts_total_ms),
                                "total_ms": round(result_turn.total_ms),
                            }
                        )
                        turn_counter += 1
                        if current_session_id:
                            record_turn(current_session_id, turn_counter, final_text, result_turn.full_text, result_turn)
                        # Drain any stale mic audio that arrived during the turn before reopening mic
                        while not transport._audio_buffer.empty():
                            try:
                                transport._audio_buffer.get_nowait()
                            except asyncio.QueueEmpty:
                                break

                        if session_active:
                            await ws.send_json({"type": "status", "state": "listening"})
                    except Exception as e:
                        logger.error(f"Pipeline turn error: {e}", exc_info=True)
                        await ws.send_json({"type": "error", "message": f"Pipeline error: {e}"})
                        while not transport._audio_buffer.empty():
                            try:
                                transport._audio_buffer.get_nowait()
                            except asyncio.QueueEmpty:
                                break
                        if session_active:
                            await ws.send_json({"type": "status", "state": "listening"})

            if not audio_feeder.done():
                audio_feeder.cancel()
        except asyncio.CancelledError:
            logger.info("Streaming STT loop cancelled")
        except Exception as e:
            logger.error(f"Streaming STT error: {e}", exc_info=True)
        finally:
            await stt.close()
            session_active = False
            logger.info("Streaming STT loop ended")

    async def batch_conversation_loop():
        """Continuous voice session loop (Fallback for batch STT providers)."""
        nonlocal session_active
        session_active = True
        logger.info("Batch conversation loop started")

        try:
            while session_active and not pipeline._cancel_event.is_set():
                try:
                    audio = await transport.read_audio()
                except asyncio.CancelledError:
                    break

                if not audio or len(audio) < 100:
                    if session_active:
                        continue
                    break

                logger.info(f"Utterance received: {len(audio)} bytes")

                user_text_captured = ""

                async def on_transcript(text: str) -> None:
                    nonlocal user_text_captured
                    user_text_captured = text
                    logger.info(f"Transcript: {text}")
                    await ws.send_json(
                        {
                            "type": "transcript",
                            "text": text,
                            "speaker": "user",
                        }
                    )

                callbacks = PipelineCallbacks(
                    on_transcript=on_transcript,
                    on_text_delta=lambda token: ws.send_json(
                        {
                            "type": "response_text",
                            "text": token,
                        }
                    ),
                    on_status=lambda state: ws.send_json(
                        {
                            "type": "status",
                            "state": state,
                        }
                    ),
                )

                try:
                    result = await pipeline.run_audio_turn(
                        audio=audio, callbacks=callbacks
                    )
                    logger.info(f"Pipeline complete: total={round(result.total_ms)}ms")

                    await ws.send_json(
                        {
                            "type": "metrics",
                            "stt_ms": round(result.stt_ms),
                            "llm_total_ms": round(result.llm_total_ms),
                            "llm_time_to_first_token_ms": round(
                                result.llm_time_to_first_token_ms
                            ),
                            "tts_time_to_first_audio_ms": round(
                                result.tts_time_to_first_audio_ms
                            ),
                            "tts_total_ms": round(result.tts_total_ms),
                            "total_ms": round(result.total_ms),
                        }
                    )

                    turn_counter += 1
                    if current_session_id:
                        record_turn(current_session_id, turn_counter, user_text_captured, result.full_text, result)

                    if session_active:
                        await ws.send_json({"type": "status", "state": "listening"})

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Pipeline error: {e}", exc_info=True)
                    await ws.send_json(
                        {"type": "error", "message": f"Pipeline error: {e}"}
                    )
                    if session_active:
                        await ws.send_json({"type": "status", "state": "listening"})

        except asyncio.CancelledError:
            logger.info("Batch conversation loop cancelled")
        finally:
            session_active = False
            logger.info("Batch conversation loop ended")

    from providers.base import StreamingSTTProvider
    is_streaming_stt = isinstance(stt, StreamingSTTProvider)

    try:
        while True:
            raw = await ws.receive()
            msg_type_bin = raw.get("type")

            if msg_type_bin == "websocket.disconnect":
                logger.info("WebSocket disconnect message received")
                break

            if msg_type_bin == "websocket.receive":
                # Binary frame = raw PCM Int16 audio from the browser
                if "bytes" in raw and raw["bytes"] is not None:
                    if conversation_task and not conversation_task.done():
                        await transport.feed_audio(raw["bytes"])
                    continue

                # Text frame = JSON control message
                text = raw.get("text")
                if not text:
                    continue
                msg = json.loads(text)
                msg_type = msg.get("type")
                logger.info(f"Received message: {msg_type}")

                if msg_type == "select_bot":
                    if session_active:
                        await ws.send_json(
                            {
                                "type": "error",
                                "message": "Cannot switch bots during an active session. Please stop the session first.",
                            }
                        )
                        continue

                    bot_id = msg.get("bot", "healthcare")
                    if bot_id in BOT_REGISTRY:
                        current_bot = bot_id
                        pipeline._agent = BOT_REGISTRY[bot_id]
                        logger.info(f"Switched active bot to: {current_bot}")
                        await ws.send_json({"type": "bot_selected", "bot": current_bot})
                        await ws.send_json({"type": "status", "state": "connected"})

                elif msg_type == "start_session":
                    if conversation_task and not conversation_task.done():
                        logger.warning("Session already active, ignoring start_session")
                        continue

                    current_session_id = str(uuid.uuid4())
                    turn_counter = 0
                    record_session_start(current_session_id, current_bot)

                    while not transport._audio_buffer.empty():
                        try:
                            transport._audio_buffer.get_nowait()
                        except asyncio.QueueEmpty:
                            break

                    pipeline.reset_cancel()
                    if is_streaming_stt:
                        conversation_task = asyncio.create_task(streaming_stt_loop())
                    else:
                        conversation_task = asyncio.create_task(batch_conversation_loop())
                    await ws.send_json({"type": "status", "state": "listening"})
                    logger.info("Session started")

                elif msg_type == "audio_chunk":
                    # Backward-compat: base64 JSON fallback (legacy clients)
                    if conversation_task and not conversation_task.done():
                        audio_b64 = msg.get("data", "")
                        if audio_b64:
                            audio_bytes = base64.b64decode(audio_b64)
                            await transport.feed_audio(audio_bytes)

                elif msg_type == "stop_session":
                    logger.info("Stopping session...")
                    session_active = False
                    if current_session_id:
                        record_session_end(current_session_id)
                        current_session_id = None
                    pipeline.cancel()

                    if conversation_task and not conversation_task.done():
                        conversation_task.cancel()
                        try:
                            await conversation_task
                        except asyncio.CancelledError:
                            pass
                        conversation_task = None

                    await transport.stop()
                    transport.set_websocket(ws)
                    await ws.send_json({"type": "status", "state": "connected"})
                    logger.info("Session stopped")

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        session_active = False
        if current_session_id:
            record_session_end(current_session_id)
            current_session_id = None
        pipeline.cancel()
        if conversation_task and not conversation_task.done():
            conversation_task.cancel()
            try:
                await conversation_task
            except asyncio.CancelledError:
                pass
        await transport.stop()

import asyncio
import base64
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("voice-agent")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.browser_transport import BrowserTransport
from core.pipeline import StreamingPipeline, PipelineCallbacks
from providers.registry import get_stt_provider, get_tts_provider
from bots.healthcare import agent as healthcare_agent
from config import load_config

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
    {"id": "travel", "name": "Travel", "enabled": False},
    {"id": "finance", "name": "Finance", "enabled": False},
    {"id": "legal", "name": "Legal", "enabled": False},
]

BOT_AGENTS = {
    "healthcare": healthcare_agent,
}


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

    pipeline = StreamingPipeline(
        bot_agent=healthcare_agent,
        transport=transport,
        tts=tts,
        stt=stt,
    )

    current_bot = "healthcare"
    conversation_task: asyncio.Task | None = None
    session_active = False

    await ws.send_json({"type": "status", "state": "connected"})
    await ws.send_json({"type": "bots", "bots": BOTS})
    logger.info("Sent initial status and bots list")

    async def conversation_loop():
        """Continuous voice session loop.

        Reads audio from the transport (which applies VAD internally),
        runs the pipeline for each detected utterance, then loops back
        to listen for the next utterance. Runs until cancelled.
        """
        nonlocal session_active
        session_active = True
        logger.info("Conversation loop started")

        try:
            while session_active and not pipeline._cancel_event.is_set():
                # Read next utterance — blocks until VAD detects speech end
                try:
                    audio = await transport.read_audio()
                except asyncio.CancelledError:
                    break

                if not audio or len(audio) < 100:
                    # Empty or too short — transport was stopped or no speech
                    if session_active:
                        continue
                    break

                logger.info(f"Utterance received: {len(audio)} bytes")

                # Build callbacks for this turn
                turn_start = __import__("time").perf_counter()
                stt_ms = 0

                async def on_transcript(text: str) -> None:
                    nonlocal stt_ms
                    # STT timing is handled inside pipeline, but we also
                    # track it here for the transcript message timestamp
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
            logger.info("Conversation loop cancelled")
        finally:
            session_active = False
            logger.info("Conversation loop ended")

    try:
        while True:
            raw = await ws.receive()
            msg_type_bin = raw.get("type")

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
                    bot_id = msg.get("bot", "healthcare")
                    if bot_id in BOT_AGENTS:
                        current_bot = bot_id
                        pipeline._agent = BOT_AGENTS[bot_id]
                        await ws.send_json({"type": "status", "state": "connected"})

                elif msg_type == "start_session":
                    if conversation_task and not conversation_task.done():
                        logger.warning("Session already active, ignoring start_session")
                        continue

                    while not transport._audio_buffer.empty():
                        try:
                            transport._audio_buffer.get_nowait()
                        except asyncio.QueueEmpty:
                            break

                    pipeline.reset_cancel()
                    conversation_task = asyncio.create_task(conversation_loop())
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
        pipeline.cancel()
        if conversation_task and not conversation_task.done():
            conversation_task.cancel()
            try:
                await conversation_task
            except asyncio.CancelledError:
                pass
        await transport.stop()

import os

import asyncio
from providers.base import Transport, STTProvider, TTSProvider
from providers.registry import get_stt_provider, get_tts_provider
from bots.healthcare import agent
from core.pipeline import StreamingPipeline, TurnResult

async def run_one_turn(
    pipeline: StreamingPipeline,
    transport: Transport,
    stt: STTProvider,
) -> bool:
    """Run one voice turn. Returns False if the user wants to quit."""
    # 1. Record
    try:
        audio = await transport.read_audio()
    except Exception as e:
        print(f"  [mic error] {e}")
        return True

    # 2. STT (outside the pipeline)
    try:
        text = await stt.transcribe(audio)
    except Exception as e:
        print(f"  [stt error] {e}")
        return True

    print(f"  You: {text}")

    # to quit the bot, the user can say "bot stop", "bot quit", or "bot exit"
    if wants_to_exit(text):
        return False

    if not text.strip():
        print("  (empty transcription, skipping)")
        return True

    # 3. Streaming turn (LLM + TTS + playback)
    try:
        result = await pipeline.run_turn(text)
    except Exception as e:
        print(f"  [pipeline error] {e}")
        return True

    print(f"  Bot: {result.full_text}")
    print(
        f"  Timing — LLM: {result.llm_total_ms:.0f}ms "
        f"(first token: {result.llm_time_to_first_token_ms:.0f}ms) | "
        f"TTS first audio: {result.tts_time_to_first_audio_ms:.0f}ms | "
        f"Total: {result.total_ms:.0f}ms"
    )
    return True


def wants_to_exit(text: str) -> bool:
    text = text.strip().lower()

    return text.startswith((
        "bot stop",
        "bot quit",
        "bot exit",
    ))
async def main():
    from core.transport import LocalTransport

    try:
        transport = LocalTransport()
        stt = get_stt_provider()
        tts = get_tts_provider()
    except Exception as e:
        print(f"Failed to initialize providers: {e}")
        return

    pipeline = StreamingPipeline(
        bot_agent=agent,
        transport=transport,
        tts=tts,
    )

    await transport.start()
    try:
        print("Healthcare Bot — say 'bot stop' to exit")
        while await run_one_turn(pipeline, transport, stt):
            pass
    except asyncio.CancelledError:
        pass
    finally:
        await transport.stop()

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
from providers.base import Transport
from providers.registry import get_stt_provider, get_tts_provider
from bots.healthcare import agent
from core.pipeline import StreamingPipeline


async def run_one_turn(
    pipeline: StreamingPipeline,
    transport: Transport,
) -> bool:
    """Run one voice turn. Returns False if the user wants to quit."""
    # 1. Record
    try:
        audio = await transport.read_audio()
    except Exception as e:
        print(f"  [mic error] {e}")
        return True

    # 2. STT — delegated to pipeline via run_audio_turn
    try:
        result = await pipeline.run_audio_turn(audio)
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

    if wants_to_exit(result.full_text):
        return False

    return True


def wants_to_exit(text: str) -> bool:
    text = text.strip().lower()
    return text.startswith(
        (
            "bot stop",
            "bot quit",
            "bot exit",
        )
    )


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
        stt=stt,
    )

    await transport.start()
    try:
        print("Healthcare Bot — say 'bot stop' to exit")
        while await run_one_turn(pipeline, transport):
            pass
    except asyncio.CancelledError:
        pass
    finally:
        await transport.stop()


if __name__ == "__main__":
    asyncio.run(main())

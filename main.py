import asyncio
import time

from providers.base import Transport, STTProvider, TTSProvider
from providers.registry import get_stt_provider, get_tts_provider
from bots.healthcare import agent

FALLBACK_MSG = "Sorry, I encountered an issue. Please try again."

async def run_one_turn(
    transport: Transport,
    stt: STTProvider,
    tts: TTSProvider,
) -> bool:
    """Run one voice turn. Returns False if the user wants to quit."""
    t0 = time.perf_counter()

    # 1. Record
    try:
        audio = await transport.read_audio()
    except Exception as e:
        print(f"  [mic error] {e}")
        return True
    t_rec = time.perf_counter()

    # 2. STT
    try:
        text = await stt.transcribe(audio)
    except Exception as e:
        print(f"  [stt error] {e}")
        return True
    t_stt = time.perf_counter()

    # Print transcript for dev visibility
    print(f"  You: {text}")

    # Quit command
    if text.strip().lower() in ("quit", "exit", "stop"):
        return False

    if not text.strip():
        print("  (empty transcription, skipping)")
        return True

    # 3. LLM
    try:
        result = await agent.run(text)
        response = result.output
    except Exception as e:
        print(f"  [llm error] {e}")
        response = FALLBACK_MSG
    t_llm = time.perf_counter()

    # Print response for dev visibility
    print(f"  Bot: {response}")

    # 4. TTS (non-streaming; streaming in Sprint 3)
    try:
        audio_out = await tts.generate_speech(response)
    except Exception as e:
        print(f"  [tts error] {e}")
        return True
    t_tts = time.perf_counter()

    # 5. Play
    try:
        played = await transport.write_audio(audio_out)
        if not played:
            print("  [speaker error] Playback failed, no audio delivered to user.")
            return True
    except Exception as e:
        print(f"  [speaker error] {e}")
        return True

    # Timing report (AI pipeline = STT + LLM + TTS)
    ai_ms = (t_tts - t_rec) * 1000
    total_ms = (time.perf_counter() - t0) * 1000
    print(f"  Timing — STT: {(t_stt-t_rec)*1000:.0f}ms | LLM: {(t_llm-t_stt)*1000:.0f}ms | TTS: {(t_tts-t_llm)*1000:.0f}ms")
    print(f"  AI pipeline: {ai_ms:.0f}ms | Total (incl. recording): {total_ms:.0f}ms")
    return True

async def main():
    from core.transport import LocalTransport

    # Initialize once — providers create SDK clients; reuse across turns
    try:
        transport = LocalTransport()
        stt = get_stt_provider()
        tts = get_tts_provider()
    except Exception as e:
        print(f"Failed to initialize providers: {e}")
        return

    await transport.start()
    try:
        print("Healthcare Bot — say 'quit' to exit")
        while await run_one_turn(transport, stt, tts):
            pass
    except asyncio.CancelledError:
        pass
    finally:
        await transport.stop()

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import sys

from providers.registry import get_tts_provider


async def main():
    text = "Hello! This is a test of Cartesia's speech synthesis. The provider pipeline is verified."
    print("Initializing TTS provider from registry...")
    tts_provider = get_tts_provider()

    print(f"Sending synthesis request for: '{text}'")
    try:
        audio_bytes = await tts_provider.generate_speech(text)

        output_path = "output.wav"
        with open(output_path, "wb") as f:
            f.write(audio_bytes)

        print(f"\nSuccess! Synthesized audio saved to: {output_path}")
        print("You can play this WAV file to verify the audio quality.")

    except Exception as e:
        print(f"An error occurred during TTS verification: {e}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import math
import os
import struct
import sys
import wave

from providers.registry import get_stt_provider


def generate_dummy_wav(filepath: str, duration_sec: float = 1.0, sample_rate: int = 16000):
    """Generate a simple 16kHz mono 16-bit PCM WAV file with a tone beep."""
    with wave.open(filepath, "wb") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit PCM (2 bytes)
        wav_file.setframerate(sample_rate)
        # Generate simple sine wave tone
        frequency = 440.0
        num_frames = int(duration_sec * sample_rate)
        for i in range(num_frames):
            value = int(32767.0 * math.sin(2.0 * math.pi * frequency * i / sample_rate))
            data = struct.pack("<h", value)
            wav_file.writeframesraw(data)


async def main():
    if len(sys.argv) > 1:
        wav_path = sys.argv[1]
        print(f"Using provided audio file: {wav_path}")
        is_dummy = False
    else:
        wav_path = "sample.wav"
        print(f"No audio file provided. Generating a dummy 1s WAV beep file at: {wav_path}")
        generate_dummy_wav(wav_path)
        is_dummy = True

    try:
        # Load audio file bytes
        with open(wav_path, "rb") as f:
            audio_data = f.read()

        # Initialize the configured STT provider
        print("Initializing STT provider from registry...")
        stt_provider = get_stt_provider()

        print("Executing transcribe call...")
        text = await stt_provider.transcribe(audio_data)

        print("\n--- Transcription Output ---")
        # Whisper may return punctuation-only (e.g. ".") for non-speech audio.
        # Strip whitespace/punctuation to detect a truly empty result.
        cleaned = text.strip().strip(".,!? ")
        if cleaned:
            print(text)
        else:
            print("(No speech detected — dummy audio contains no spoken words)")
        print("----------------------------\n")

    except Exception as e:
        print(f"An error occurred during verification: {e}", file=sys.stderr)

    finally:
        # Clean up generated dummy WAV
        if is_dummy and os.path.exists(wav_path):
            os.remove(wav_path)
            print("Cleaned up dummy WAV file.")


if __name__ == "__main__":
    asyncio.run(main())

Here's the relative version of the walkthrough:

# Sprint 1 Walkthrough - Real Calls & Interfaces

We have completed the implementation of the Sprint 1 plan. Here is a summary of the changes and how to verify them.

## Changes Made

### Configuration
- `config.py`: Added `cartesia_model_id` (default `"sonic-3.5"`) to settings for customization.

### Providers Layer
- `providers/base.py`: Defined abstract interfaces (`Transport`, `STTProvider`, `TTSProvider`, `LLMProvider`, and `EmbeddingProvider`).
- `providers/groq.py`:
  - `GroqWhisperSTT` wraps Pipecat's `GroqSTTService` instance (in `self.service`), but calls the official `AsyncGroq` client for its public `transcribe()` method to prevent private internal dependencies.
  - `GroqLLM` returns PydanticAI's `GroqModel` instance configured with settings.
- `providers/cartesia.py`:
  - `CartesiaTTS` wraps Pipecat's `CartesiaTTSService` instance, but calls the official `AsyncCartesia` client for `generate_speech()` and `generate_speech_stream()` methods.
- `providers/registry.py`: Implemented registry functions (`get_stt_provider()`, `get_tts_provider()`, `get_llm_provider()`) to fetch instances dynamically based on settings.

### Verification Scripts
- `scripts/test_groq_stt.py`: Verification script that generates a short, dummy 16kHz WAV tone (if no file is supplied as arguments) and transcribes it using `GroqWhisperSTT`.
- `scripts/test_cartesia_tts.py`: Verification script that synthesizes text to a WAV audio file (`output.wav`) using `CartesiaTTS`.

---

## Verification Steps (For User to Execute)

Ensure your `.env` contains:
```env
GROQ_API_KEY=your_key_here
CARTESIA_API_KEY=your_key_here
CARTESIA_VOICE_ID=your_voice_id_here
```

### 1. Test STT Transcription
Run the transcription verification script (this will auto-generate a `sample.wav` beep tone to verify API connectivity):
```bash
uv run python scripts/test_groq_stt.py
```
*(Optionally, pass a path to a real speech WAV file to verify transcription accuracy: `uv run python scripts/test_groq_stt.py path/to/your/speech.wav`)*

### 2. Test TTS Synthesis
Run the text-to-speech verification script:
```bash
uv run python scripts/test_cartesia_tts.py
```
This generates `output.wav` in the root directory. You can play `output.wav` to listen to the synthesized speech.
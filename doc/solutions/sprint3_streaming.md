# Sprint 3 — Streaming Pipeline Walkthrough

Sprint 3 has been implemented successfully, replacing the batch-style generation and playback with a fully streaming pipeline.

## Changes Made

### 1. Unified Interface Updates
- **providers/base.py**:
  - Added `AudioFormat` dataclass.
  - Added abstract `play_stream` method to the `Transport` interface.
  - Added `audio_format` abstract property to the `TTSProvider` interface.

### 2. Transport & Provider Implementations
- **core/transport.py**:
  - Implemented `play_stream` on `LocalTransport` using `sounddevice.RawOutputStream`.
- **providers/cartesia.py**:
  - Added `audio_format` property returning sample rate `44100`, channel count `1`, and dtype `float32`.

### 3. Core Streaming Pipeline
- **core/pipeline.py** (NEW):
  - Created `TextChunker` to segment LLM streaming deltas at sentence/clause boundaries for high-quality TTS generation.
  - Created `StreamingPipeline` utilizing `asyncio.gather` to concurrently execute LLM generation, TTS streaming, and audio playback.
  - Created `TurnResult` to capture latency metrics: `llm_time_to_first_token_ms`, `llm_total_ms`, `tts_time_to_first_audio_ms`, and `total_ms`.

### 4. Interactive Command-Line Loop
- **main.py**:
  - Wired `StreamingPipeline` into `run_one_turn` and `main` functions.
  - Replaced the sequential flow with `pipeline.run_turn()`.

---

## Verification Results
- Verified that files compile successfully.
- Verified speech synthesis via `test_cartesia_tts.py` successfully connects to Cartesia and outputs a valid WAV.
- Verified heuristic chunk boundaries and flush logic with unit tests in `test_chunker.py`.
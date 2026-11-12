# Technical Specification: Voice Agent

## Overview

### Resume Focus Areas
- Real-Time Full-Duplex Audio Streaming Architecture
- Sentence-Boundary & Clause Heuristic Chunking for Latency Optimization
- Asynchronous Event-Driven Pipeline Engineering (`asyncio.Queue`, `asyncio.gather`, producer-consumer coroutines)
- Retrieval-Augmented Generation (RAG) Systems Integration (PostgreSQL + `pgvector`, Jina AI v5 Embeddings)
- WebSocket Transport Protocol & Energy-Based VAD Implementation (Int16 RMS Sliding Window)
- Pydantic Settings & PydanticAI Agent Instrumentation

### Purpose
Voice Agent is a low-latency, multi-domain streaming conversational AI application designed to provide sub-second time-to-first-audio (TTFA / Time-to-Ear) voice interactions between users and specialized AI domain agents.

### Problem Solved
Traditional voice assistant architectures execute sequentially in discrete batches:
$$\text{Full Audio Capture} \longrightarrow \text{Batch STT} \longrightarrow \text{Full LLM Generation} \longrightarrow \text{Batch TTS Synthesis} \longrightarrow \text{Playback}$$
This pattern yields user-perceived latencies of 3,000–6,000ms per conversational turn.

Voice Agent solves this bottleneck by orchestrating an overlapped, concurrent streaming pipeline:
- As the user speaks, browser Web Audio captures Int16 mono PCM and streams it via WebSocket.
- Server-side sliding RMS Energy VAD detects speech end in real time.
- Groq Whisper transcribes the utterance.
- PydanticAI streams LLM tokens; tokens are buffered into a linguistic clause/sentence heuristic chunker ([TextChunker](file:///c:/Users/vishn/PROJECT/voice-agent/core/pipeline.py#L8)).
- Chunks are immediately streamed into Cartesia Sonic TTS over full-duplex WebSockets.
- Synthesized Float32 PCM audio chunks stream concurrently back to the browser Web Audio buffer while the LLM is still generating subsequent tokens.

### Target Users
- **Voice UI Developers & AI Engineers:** Developers seeking production-grade, provider-agnostic Python architectures for low-latency conversational agents.
- **Enterprise Demonstrations:** Real-time domain assistants (Healthcare Triage, Travel Booking, Finance, Legal Counsel, Jira IT Operations).

### Core Features
- **Multi-Domain Bot Engine:** Specialized PydanticAI agents equipped with domain system prompts and tools ([bots/](file:///c:/Users/vishn/PROJECT/voice-agent/bots/)).
- **Sentence/Clause Boundary Chunker:** Heuristic buffer ([TextChunker](file:///c:/Users/vishn/PROJECT/voice-agent/core/pipeline.py#L8)) flushing tokens on sentence boundaries (`. `, `! `, `? `), clause boundaries (`, `, `; `, `: `) when buffer reaches half capacity, or hard size limits.
- **Provider-Agnostic Core:** Modular plugin architecture supporting Groq Whisper (STT), Groq Llama 3.3 70B (LLM), Cartesia Sonic 3.5 (TTS), and Jina AI / OpenAI (Embeddings).
- **Energy-Based VAD & Browser Transport:** Continuous WebSocket connection ([BrowserTransport](file:///c:/Users/vishn/PROJECT/voice-agent/core/browser_transport.py)) applying Int16 RMS energy processing for voice activity detection, warmup filtering, and silence termination.
- **Contextual RAG Integration:** Similarity search engine utilizing cosine distance `<=>` over Jina AI text embeddings stored in PostgreSQL with `pgvector` ([retrieval.py](file:///c:/Users/vishn/PROJECT/voice-agent/core/retrieval.py)).

---

# Architecture & System Design

### High-Level Architecture

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                                   Browser SPA                                     │
│  ┌───────────────────────────┐                     ┌───────────────────────────┐  │
│  │ AudioWorklet (16kHz Int16)│                     │  Web Audio Buffer (Float) │  │
│  └─────────────┬─────────────┘                     └─────────────▲─────────────┘  │
└────────────────┼─────────────────────────────────────────────────┼────────────────┘
                 │ WebSocket (Binary Int16 PCM)                    │ WebSocket (JSON / Base64 Float32)
                 ▼                                                 │
┌──────────────────────────────────────────────────────────────────┴────────────────┐
│                                  FastAPI Backend                                  │
│ ┌───────────────────────────────────────────────────────────────────────────────┐ │
│ │                              BrowserTransport                                 │ │
│ │         (Energy RMS VAD / Sliding Window / Silence & Noise Rejection)         │ │
│ └──────────────────────────────────────┬────────────────────────────────────────┘ │
│                                        │ WAV Utterance Blob                       │
│                                        ▼                                          │
│ ┌───────────────────────────────────────────────────────────────────────────────┐ │
│ │                             StreamingPipeline                                 │ │
│ │  ┌───────────────┐      ┌──────────────────────────┐      ┌─────────────────┐ │ │
│ │  │ STT Provider  │ ───► │   PydanticAI Domain Bot  │ ───► │  TTS Provider   │ │ │
│ │  │ (Groq Whisper)│      │ (Groq Llama 3.3 + Tools) │      │ (Cartesia Sonic)│ │ │
│ │  └───────────────┘      └────────────┬─────────────┘      └─────────────────┘ │ │
│ └──────────────────────────────────────┼────────────────────────────────────────┘ │
└────────────────────────────────────────┼──────────────────────────────────────────┘
                                         │ Embedding / Cosine Search (<=>)
                                         ▼
                            ┌──────────────────────────┐
                            │ PostgreSQL + pgvector    │
                            │ (finance / legal / jira) │
                            └──────────────────────────┘
```

### Data Flow

1. **Audio Capture:** The frontend microphone captures audio via `AudioWorklet` (`audio-processor.js`), resamples to 16kHz mono `Int16 PCM`, and emits raw binary buffers over WebSocket every 100ms.
2. **VAD Processing:** [`BrowserTransport.read_audio()`](file:///c:/Users/vishn/PROJECT/voice-agent/core/browser_transport.py#L60) consumes frames from an `asyncio.Queue`, computes RMS energy over 100ms sliding windows ($\text{RMS} = \sqrt{\frac{1}{N}\sum x_i^2}$), detects speech start (`RMS > 200.0`), counts silence chunks (`silence_duration = 2.0s`), enforces noise rejection (`min_speech_duration = 0.3s`), and returns a complete `WAV` byte container.
3. **Speech-to-Text:** The complete WAV blob is dispatched to [`GroqWhisperSTT`](file:///c:/Users/vishn/PROJECT/voice-agent/providers/groq.py#L11) (`whisper-large-v3-turbo`) returning text transcript.
4. **Context Retrieval (RAG):** When tools are called (e.g. `search_finance_docs`, `search_legal_docs`, `search_jira_docs`), Jina AI converts query text into a 1024-dim vector and queries PostgreSQL with cosine distance operator `<=>`.
5. **Streaming LLM & Chunking:** The prompt is processed by the selected domain PydanticAI bot via `agent.run_stream()`. As tokens stream, [`TextChunker`](file:///c:/Users/vishn/PROJECT/voice-agent/core/pipeline.py#L8) buffers deltas until sentence boundaries (`. `, `! `, `? `) or clause boundaries (`, `, `; `, `: `) are identified.
6. **Concurrent TTS Synthesis & Playback:** Each flushed chunk is pushed into `CartesiaTTS.generate_speech_stream()`. Synthesized `pcm_f32le` chunks are streamed directly to the client WebSocket, where the React Web Audio API schedules gapless playback using `ctx.currentTime`.

---

# Complete File-by-File Technical Breakdown

| File Path | Role & Key Responsibilities | Key Dependencies & APIs |
|---|---|---|
| [`config.py`](file:///c:/Users/vishn/PROJECT/voice-agent/config.py) | Centralized application configuration. Reads `.env` via Pydantic `BaseSettings` / `SettingsConfigDict`. Computes provider mapping strings. | `pydantic`, `pydantic_settings`, `functools.lru_cache` |
| [`main.py`](file:///c:/Users/vishn/PROJECT/voice-agent/main.py) | CLI entry point for local microphone/speaker voice loop. Configures Windows Selector Event Loop policy and executes turn loop. | `argparse`, `asyncio`, `sounddevice`, `core.transport` |
| [`backend/api.py`](file:///c:/Users/vishn/PROJECT/voice-agent/backend/api.py) | FastAPI server exposing `/health` and WebSocket `/ws`. Manages client session lifecycle, binary audio frames, control frames (`start_session`, `select_bot`, `stop_session`), and dispatches pipeline turns. | `fastapi`, `uvicorn`, `starlette.websockets` |
| [`backend/run.py`](file:///c:/Users/vishn/PROJECT/voice-agent/backend/run.py) | Execution launcher for FastAPI uvicorn development server (`0.0.0.0:8000`). | `uvicorn` |
| [`core/pipeline.py`](file:///c:/Users/vishn/PROJECT/voice-agent/core/pipeline.py) | Core streaming turn engine. Implements `TextChunker`, `TurnResult`, `PipelineCallbacks`, and `StreamingPipeline._run_turn()` using `asyncio.gather()` over 3 concurrent coroutines (`llm_producer`, `tts_bridge`, `play_stream`). Handles cancellation events. | `asyncio`, `time`, `dataclasses` |
| [`core/browser_transport.py`](file:///c:/Users/vishn/PROJECT/voice-agent/core/browser_transport.py) | WebSocket audio transport. Implements sliding-window RMS energy VAD (`read_audio`) over incoming `Int16` buffers, wraps WAV headers, and streams base64 Float32 audio chunks (`play_stream`). | `numpy`, `wave`, `io`, `asyncio` |
| [`core/transport.py`](file:///c:/Users/vishn/PROJECT/voice-agent/core/transport.py) | Local hardware transport for CLI. Records microphone input with `sounddevice.InputStream` in a worker thread (`asyncio.to_thread`) and plays output using `sounddevice.RawOutputStream`. Supports custom WAV header parsing. | `sounddevice`, `numpy`, `wave`, `asyncio` |
| [`core/retrieval.py`](file:///c:/Users/vishn/PROJECT/voice-agent/core/retrieval.py) | Async vector search over PostgreSQL `pgvector` tables (`finance_docs`, `legal_docs`, `jira_docs`) using `<=>` cosine distance. Single source of truth for `DOMAIN_TABLE_MAP`. | `psycopg`, `pgvector.psycopg` |
| [`core/ingestion.py`](file:///c:/Users/vishn/PROJECT/voice-agent/core/ingestion.py) | Document chunking (`chunk_document` paragraph/sentence boundary logic), batch embedding generation, and asynchronous database insertion with JSONB metadata. | `psycopg`, `pgvector`, `datetime` |
| [`db/session.py`](file:///c:/Users/vishn/PROJECT/voice-agent/db/session.py) | SQLAlchemy ORM session factory and schema initialization (`init_db`). Declares `CallSession`, `Turn` models and enables `vector` extension. | `sqlalchemy`, `pgvector` |
| [`providers/base.py`](file:///c:/Users/vishn/PROJECT/voice-agent/providers/base.py) | Abstract Base Classes defining strict provider interfaces: `Transport`, `STTProvider`, `TTSProvider`, `LLMProvider`, `EmbeddingProvider`, and `AudioFormat` dataclass. | `abc`, `dataclasses`, `pydantic_ai.models` |
| [`providers/registry.py`](file:///c:/Users/vishn/PROJECT/voice-agent/providers/registry.py) | Factory registry dispatching provider instances (`get_stt_provider`, `get_tts_provider`, `get_llm_provider`, `get_embedding_provider`) based on configuration strings. | `config` |
| [`providers/groq.py`](file:///c:/Users/vishn/PROJECT/voice-agent/providers/groq.py) | Groq integrations: `GroqWhisperSTT` (AsyncGroq `audio.transcriptions.create`) and `GroqLLM` (`pydantic_ai.models.groq.GroqModel`). | `groq`, `pydantic_ai` |
| [`providers/cartesia.py`](file:///c:/Users/vishn/PROJECT/voice-agent/providers/cartesia.py) | Cartesia Sonic TTS integration. Implements bidirectional WebSocket streaming via `AsyncCartesia.tts.websocket_connect()` with concurrent sender/receiver tasks. | `cartesia.AsyncCartesia`, `asyncio` |
| [`providers/jina.py`](file:///c:/Users/vishn/PROJECT/voice-agent/providers/jina.py) | Jina AI REST embedding integration supporting single (`retrieval.query`) and batch (`retrieval.passage`) embeddings with index sorting. | `httpx` |
| [`providers/openai.py`](file:///c:/Users/vishn/PROJECT/voice-agent/providers/openai.py) | Optional OpenAI embedding provider (`text-embedding-3-small`). | `openai.AsyncOpenAI` |
| [`bots/__init__.py`](file:///c:/Users/vishn/PROJECT/voice-agent/bots/__init__.py) | Exports `BOT_REGISTRY` mapping domain names (`healthcare`, `travel`, `finance`, `legal`, `jira`) to agent instances. | `bots.*` |
| [`bots/healthcare.py`](file:///c:/Users/vishn/PROJECT/voice-agent/bots/healthcare.py) | Healthcare assistant with clinical triage guardrails (no direct diagnosis/prescription, emergency service handoff). | `pydantic_ai.Agent` |
| [`bots/travel.py`](file:///c:/Users/vishn/PROJECT/voice-agent/bots/travel.py) | Travel assistant equipped with `@agent.tool_plain` `search_flights(origin, destination, date)`. | `pydantic_ai.Agent` |
| [`bots/finance.py`](file:///c:/Users/vishn/PROJECT/voice-agent/bots/finance.py) | Financial assistant equipped with `@agent.tool_plain` `search_finance_docs(query)`. | `pydantic_ai.Agent`, `core.retrieval` |
| [`bots/legal.py`](file:///c:/Users/vishn/PROJECT/voice-agent/bots/legal.py) | Legal assistant with disclaimer guardrails and `@agent.tool_plain` `search_legal_docs(query)`. | `pydantic_ai.Agent`, `core.retrieval` |
| [`bots/jira.py`](file:///c:/Users/vishn/PROJECT/voice-agent/bots/jira.py) | Jira IT operations assistant with `@agent.tool_plain` `search_jira_docs(query)` querying pgvector. | `pydantic_ai.Agent`, `core.retrieval` |
| [`scripts/benchmark.py`](file:///c:/Users/vishn/PROJECT/voice-agent/scripts/benchmark.py) | Isolated and end-to-end benchmark suite measuring STT latency, LLM TTFT, TTS TTFA, and Time-to-Ear (TTE). | `asyncio`, `statistics`, `wave` |
| [`scripts/seed_data.py`](file:///c:/Users/vishn/PROJECT/voice-agent/scripts/seed_data.py) | Ingestion pipeline fetching real SEC Apple 10-K, CFPB guides, Common Paper NDAs, and Apache Jira tickets into pgvector. | `httpx`, `core.ingestion` |
| [`frontend/public/audio-processor.js`](file:///c:/Users/vishn/PROJECT/voice-agent/frontend/public/audio-processor.js) | AudioWorklet processor running on audio render thread. Resamples mic audio to 16kHz, converts Float32 to Int16, and transfers ArrayBuffers with zero-copy. | `AudioWorkletProcessor` |
| [`frontend/src/hooks/useWebSocket.ts`](file:///c:/Users/vishn/PROJECT/voice-agent/frontend/src/hooks/useWebSocket.ts) | Custom React hook managing WebSocket connection, mic state gating (`connectionStateRef` preventing acoustic echo), and seamless gapless audio scheduling (`AudioContext.currentTime`). | `react`, Web Audio API |
| [`frontend/src/hooks/useAudio.ts`](file:///c:/Users/vishn/PROJECT/voice-agent/frontend/src/hooks/useAudio.ts) | React hook capturing `getUserMedia` audio and wiring it into `AudioWorkletNode` without connecting to destination (echo prevention). | Web Audio API |

---

# Traps & Tricky Pydantic / PydanticAI Uses

### 1. Pydantic V2 Settings & Environment Precedence Trap
In [`config.py`](file:///c:/Users/vishn/PROJECT/voice-agent/config.py#L9-L14):
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
```
- **Trap / Gotcha:** In Pydantic V2, `BaseSettings` lives in `pydantic_settings` (not `pydantic`). Furthermore, if a property has no default and is missing from `.env` or system environment variables, instantiation raises a `ValidationError` immediately upon import or initialization.
- **Trap:** System environment variables take precedence over `.env` files. If `GROQ_API_KEY` exists in the OS environment, it overrides `.env`.
- **Property Caching:** Calling `load_config()` repeatedly can incur `.env` parsing overhead. Using `@lru_cache` ensures a single immutable settings instance across the runtime.

### 2. PydanticAI `Agent` Construction vs Runtime Context
In domain bots (e.g. [`bots/jira.py`](file:///c:/Users/vishn/PROJECT/voice-agent/bots/jira.py#L17-L21)):
```python
agent = Agent(
    model=get_llm_provider().get_model(),
    system_prompt=SYSTEM_PROMPT,
    output_type=str,
)
```
- **Tricky Pattern (`output_type=str`):** By default, PydanticAI agents can validate structured outputs using Pydantic models. However, for real-time voice streaming with `run_stream()`, `output_type=str` is required so that raw text deltas can be emitted token-by-token. If a structured Pydantic model is set as `output_type`, token deltas cannot be directly piped to TTS until the full JSON model completes validation.
- **Module-Level Instantiation Trap:** `get_llm_provider().get_model()` is executed at module import time. If API keys are loaded or mutated dynamically after import, the model instance holds a stale client unless re-instantiated.

### 3. `@agent.tool_plain` vs `@agent.tool` in PydanticAI
In [`bots/jira.py`](file:///c:/Users/vishn/PROJECT/voice-agent/bots/jira.py#L24) and [`bots/travel.py`](file:///c:/Users/vishn/PROJECT/voice-agent/bots/travel.py#L15):
```python
@agent.tool_plain
async def search_jira_docs(query: str) -> str:
    ...
```
- **Tricky Difference:** In PydanticAI, `@agent.tool` injects `RunContext[Deps]` as the first argument to the tool function. If the function does not accept `ctx: RunContext`, PydanticAI will fail at runtime with a signature mismatch error.
- **Why `@agent.tool_plain` is used:** When tools do not require dependency injection via `RunContext`, `@agent.tool_plain` must be used instead.
- **Type Hints as JSON Schema:** PydanticAI automatically inspects python type annotations (`query: str`, `date: str`) and docstrings to build the tool's JSON Schema for the LLM function-calling interface. Missing type hints will cause agent registration errors.

### 4. PydanticAI Streaming Context Manager Lifecycle
In [`core/pipeline.py`](file:///c:/Users/vishn/PROJECT/voice-agent/core/pipeline.py#L206-L278):
```python
async with self._agent.run_stream(text) as response:
    # 1. Stream tokens
    async for token in response.stream_text(delta=True):
        ...
    # 2. Get output MUST be called inside the context manager
    full_text = await response.get_output()
```
- **Trap:** `response.stream_text(delta=True)` yields only incremental deltas. Calling `await response.get_output()` after exiting the `async with` block raises a runtime error because the underlying HTTP stream connection is closed on context exit.
- **Delta vs Cumulated Text:** If `delta=False` is passed (the default), `stream_text()` yields the entire accumulated string so far at each step (e.g. `"Hello"`, `"Hello world"`), which breaks chunking and causes repetitive audio synthesis!

---

# Asyncio & Concurrency In-Depth Questions & Scenarios

### Q1: How does `StreamingPipeline` prevent head-of-line blocking and achieve sub-600ms Time-to-Ear (TTE)?
**Answer:**
`StreamingPipeline._run_turn()` spawns 3 concurrent coroutines via `asyncio.gather()`:
1. `llm_producer()`: Consumes LLM token deltas from `response.stream_text(delta=True)` and pushes them into an `asyncio.Queue[str | None]` (`text_queue`).
2. `tts_bridge()`: Consumes from `text_queue`, runs the `TextChunker` heuristic, and feeds completed clauses into Cartesia's streaming WebSocket, pushing audio chunks into `audio_queue`.
3. `transport.play_stream()`: Reads from `audio_queue` and sends audio frames to the client WebSocket immediately.

Because these tasks run concurrently on the asyncio event loop and communicate via bounded queues with sentinels (`None`), TTS synthesis and client audio playback begin as soon as the first clause (e.g. 5–10 tokens) is produced, while the LLM is still generating subsequent tokens.

```
Time ──►
LLM:       [Token 1..10 (Clause 1)] ──► [Token 11..25 (Clause 2)] ──► [Token 26..40]
TTS:                                    [Synthesize Clause 1]     ──► [Synthesize Clause 2]
Playback:                                                         ──► [Play Clause 1 Audio]
```

### Q2: What is the purpose of the `None` sentinel in `asyncio.Queue` pipelines, and what happens if an exception occurs before the sentinel is sent?
**Answer:**
An `asyncio.Queue` does not have a native "closed" state. Consumers iterating over an `asyncio.Queue` will block indefinitely on `await queue.get()`.
- A sentinel value (conventionally `None`) is pushed by the producer when iteration finishes to signal termination.
- **The Deadlock Trap:** If an unhandled exception occurs in `llm_producer` before `await text_queue.put(None)` executes, `tts_bridge` will await `text_queue.get()` forever, deadlocking the turn.
- **Solution:** In [`core/pipeline.py`](file:///c:/Users/vishn/PROJECT/voice-agent/core/pipeline.py#L252), `await audio_queue.put(None)` is wrapped in a `finally` block to guarantee sentinel propagation even during cancellations or errors.

### Q3: Why does `BrowserTransport.read_audio()` need to run sliding RMS calculations, and why is `asyncio.wait_for()` with a 1.0s timeout used?
**Answer:**
`BrowserTransport` acts as an async audio buffer. Raw frames arrive over the WebSocket and are placed in `_audio_buffer`.
- The `read_audio()` loop executes `await asyncio.wait_for(self._audio_buffer.get(), timeout=1.0)`.
- If the browser stops sending audio or experiences packet drops without closing the socket, `wait_for` prevents `read_audio()` from hanging forever.
- It slices incoming bytes into $100\text{ms}$ windows ($16000\text{ Hz} \times 2\text{ bytes} \times 0.1\text{s} = 3200\text{ bytes}$), calculates RMS energy via `np.sqrt(np.mean(samples**2))`, and manages state transitions (`warmup`, `speech_started`, `silence_chunks`).

### Q4: How is User Barge-In (Interrupting the Assistant) implemented across asyncio and WebSockets?
**Answer:**
When the user speaks or clicks stop:
1. The server triggers `pipeline.cancel()`, which sets `self._cancel_event` (`asyncio.Event`).
2. Both `llm_producer` and `tts_bridge` poll `if self._cancel_event.is_set(): break`.
3. In [`backend/api.py`](file:///c:/Users/vishn/PROJECT/voice-agent/backend/api.py#L241-L248), `conversation_task.cancel()` cancels the enclosing turn task.
4. On the frontend, [`useWebSocket.ts`](file:///c:/Users/vishn/PROJECT/voice-agent/frontend/src/hooks/useWebSocket.ts#L202-L205) iterates through all scheduled `AudioBufferSourceNode` objects in `activeSourcesRef.current` and calls `src.stop()`, clearing the audio queue instantly.

### Q5: What is Acoustic Feedback / Phantom Transcription Echo, and how does the code prevent it?
**Answer:**
If the user's microphone is open while the bot's synthesized audio plays through speakers, the microphone records the assistant's own voice and re-transcribes it as the next user query (e.g. producing "Thank you", "Goodbye", or gibberish loops).
- **Prevention 1 (Client Gating in [`useWebSocket.ts`](file:///c:/Users/vishn/PROJECT/voice-agent/frontend/src/hooks/useWebSocket.ts#L182)):** `sendAudioChunk()` checks `connectionStateRef.current !== 'listening'`. If the state is `'speaking'` or `'thinking'`, mic frames are dropped immediately before sending over the WebSocket.
- **Prevention 2 (Web Audio Routing in [`useAudio.ts`](file:///c:/Users/vishn/PROJECT/voice-agent/frontend/src/hooks/useAudio.ts#L39)):** The `AudioWorkletNode` is connected to the media stream source but NOT to `AudioContext.destination`.

### Q6: Why is `asyncio.WindowsSelectorEventLoopPolicy()` required on Windows in `main.py` and `scripts/`?
**Answer:**
On Python 3.8+ on Windows, the default event loop policy is `ProactorEventLoop` (I/O Completion Ports). While great for high-throughput networking, `ProactorEventLoop` has known compatibility issues with certain C extensions, subprocesses, and keyboard interrupt signals. Setting `WindowsSelectorEventLoopPolicy` ensures stable socket polling and graceful `KeyboardInterrupt` handling.

---

# Verification & Test Strategy

To verify the entire voice agent system:

1. **Unit & Isolated Provider Tests:**
   ```bash
   # Test STT transcription
   python scripts/test_groq_stt.py

   # Test Cartesia TTS audio generation
   python scripts/test_cartesia_tts.py

   # Test PydanticAI streaming response
   python scripts/test_stream.py
   ```

2. **Database & Knowledge Base Seeding:**
   ```bash
   # Seed PostgreSQL pgvector with real 10-K, CFPB, NDA, and Jira data
   python scripts/seed_data.py
   ```

3. **Performance & Latency Benchmarks:**
   ```bash
   # Run full 4-stage benchmark suite (STT, LLM, TTS, E2E Time-to-Ear)
   python scripts/benchmark.py --iterations 3
   ```

4. **Full Web System Verification:**
   - Backend: `uvicorn backend.api:app --reload --port 8000`
   - Frontend: `cd frontend && npm run dev`
   - Connect via browser to `http://localhost:5173`, select domain bots, start voice session, and verify full-duplex conversational streaming.

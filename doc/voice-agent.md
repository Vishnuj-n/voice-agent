# Technical Specification: Voice Agent

## Overview

### Resume Focus Areas
- Real-Time Audio Streaming Architecture
- Sentence-Boundary Chunking & Latency Optimization
- Asynchronous Event-Driven Pipeline Engineering
- Retrieval-Augmented Generation (RAG) Systems Integration
- WebSocket Transport Protocol & Energy-Based VAD Implementation

### Purpose
Voice Agent is a multi-domain streaming conversational AI application designed to demonstrate low-latency, natural voice interactions between users and specialized AI agents.

### Problem Solved
Traditional voice assistant architectures rely on sequential batch processing (full audio recording ➔ batch STT ➔ full LLM text response ➔ full TTS audio synthesis ➔ playback). This pattern yields user-perceived latencies of several seconds per turn. Voice Agent addresses this bottleneck by implementing a streaming pipeline that overlaps transcribing, text generation, RAG document retrieval, and audio chunk synthesis to minimize time-to-first-audio (TTFA).

### Target Users
- **Voice UI Developers & AI Enthusiasts:** Developers exploring open, provider-agnostic Python architectures for low-latency conversational agents.
- **Interactive Demonstrations:** Users testing real-time voice interactions across domain topics (Healthcare, Travel, Finance, Legal, Jira IT Operations).

### Core Features
- **Multi-Domain Bot Engine:** Specialized PydanticAI agents equipped with domain system prompts and tools ([bots](file:///c:/Users/vishn/PROJECT/voice-agent/bots/)).
- **Streaming Pipeline:** Sentence-clause heuristic buffer ([TextChunker](file:///c:/Users/vishn/PROJECT/voice-agent/core/pipeline.py#L8-L53)) streaming token deltas to TTS as soon as viable linguistic units complete.
- **Provider-Agnostic Core:** Modular plugin interface supporting Groq Whisper (STT), Groq Llama 3.3 70B / 3.1 8B (LLM), Cartesia Sonic (TTS), and Jina AI / OpenAI (Embeddings).
- **Energy-Based VAD & Browser Transport:** Continuous WebSocket connection ([BrowserTransport](file:///c:/Users/vishn/PROJECT/voice-agent/core/browser_transport.py)) applying Int16 RMS energy processing for voice activity detection and silence termination.
- **Contextual RAG Integration:** Similarity search engine utilizing cosine similarity over Jina AI text embeddings ([retrieval.py](file:///c:/Users/vishn/PROJECT/voice-agent/core/retrieval.py)).

---

# Architecture

### High-Level Architecture
The system consists of a frontend React SPA communicating over a persistent WebSocket with a FastAPI backend. Audio PCM streams from the user's microphone pass through client/server energy VAD. Once speech end is detected, the server pipelines transcribing via Groq Whisper, injects retrieved RAG context into a PydanticAI domain agent, streams LLM output deltas through a sentence chunker into Cartesia TTS, and streams synthesized PCM audio chunks back to the browser.

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                                   Browser SPA                                     │
│     ┌──────────────────────┐                     ┌──────────────────────────┐     │
│     │  Microphone (PCM)    │                     │   Audio Player (PCM)     │     │
│     └──────────┬───────────┘                     └────────────▲─────────────┘     │
└────────────────┼──────────────────────────────────────────────┼───────────────────┘
                 │ WebSocket (Int16 PCM)                        │ WebSocket (PCM Chunks)
                 ▼                                              │
┌───────────────────────────────────────────────────────────────┴───────────────────┐
│                                  FastAPI Backend                                  │
│ ┌───────────────────────────────────────────────────────────────────────────────┐ │
│ │                              BrowserTransport                                 │ │
│ │                (Energy RMS VAD / Silence Detection Windowing)                 │ │
│ └──────────────────────────────────────┬────────────────────────────────────────┘ │
│                                        │ WAV Utterance Blob                       │
│                                        ▼                                          │
│ ┌───────────────────────────────────────────────────────────────────────────────┐ │
│ │                             StreamingPipeline                                 │ │
│ │  ┌───────────────┐      ┌──────────────────────────┐      ┌─────────────────┐ │ │
│ │  │ STT Provider  │ ───► │   PydanticAI Domain Bot  │ ───► │  TTS Provider   │ │ │
│ │  │ (Groq Whisper)│      │  (Groq Llama 3.3 + RAG)  │      │ (Cartesia Sonic)│ │ │
│ │  └───────────────┘      └────────────┬─────────────┘      └─────────────────┘ │ │
│ └──────────────────────────────────────┼────────────────────────────────────────┘ │
└────────────────────────────────────────┼──────────────────────────────────────────┘
                                         │ Embedding / Cosine Search
                                         ▼
                            ┌──────────────────────────┐
                            │ Vector DB / Jina Embeds  │
                            └──────────────────────────┘
```

### Data Flow

1. **Audio Capture:** The frontend captures microphone audio (`Float32`), converts it to mono `Int16 PCM` at 16kHz, and emits base64 chunks over WebSocket.
2. **VAD Processing:** [`BrowserTransport.read_audio()`](file:///c:/Users/vishn/PROJECT/voice-agent/core/browser_transport.py#L60-L150) aggregates incoming frames, computes RMS energy over 100ms sliding windows, detects speech start/end boundaries, and constructs a WAV audio container.
3. **Speech-to-Text:** The complete WAV blob is dispatched to [`GroqSTTProvider`](file:///c:/Users/vishn/PROJECT/voice-agent/providers/groq.py) (`whisper-large-v3-turbo`) returning text transcript.
4. **Retrieval-Augmented Generation:** Relevant domain knowledge is fetched via [`retrieve_context()`](file:///c:/Users/vishn/PROJECT/voice-agent/core/retrieval.py#L29-L55) using Jina AI embedding vector search.
5. **Streaming LLM & Chunking:** The prompt is processed by the selected domain PydanticAI bot. As tokens stream back, [`TextChunker`](file:///c:/Users/vishn/PROJECT/voice-agent/core/pipeline.py#L8-L53) buffers deltas until sentence boundaries (`.`, `!`, `?`) or clause boundaries (`,`, `;`, `:`) are identified.
6. **TTS Synthesis & Output Transport:** Each flushed sentence chunk is sent to [`CartesiaTTSProvider`](file:///c:/Users/vishn/PROJECT/voice-agent/providers/cartesia.py) (`sonic-3.5`). Audio chunks stream directly to the client WebSocket for real-time playout.

---

# Tech Stack

### Python 3.13 / FastAPI / Uvicorn
- **Why chosen:** Asynchronous I/O execution natively suited for concurrent WebSocket connections and streaming network requests.
- **Alternatives considered:** Node.js (TypeScript), Go.
- **Trade-offs:** Python offers rich AI library integration (PydanticAI, NumPy) at the expense of higher per-thread memory usage compared to compiled runtimes.

### Groq API (`whisper-large-v3-turbo` & `llama-3.3-70b-versatile`)
- **Why chosen:** LPU (Language Processing Unit) infrastructure delivers fast Time-to-First-Token (TTFT) and streaming generation rates for conversational voice tasks.
- **Alternatives considered:** OpenAI API, local vLLM deployments.
- **Trade-offs:** External API dependency with usage rate limits, avoiding local GPU hosting requirements.

### Cartesia (`sonic-3.5`)
- **Why chosen:** Native byte-level streaming support and low-latency audio generation designed for conversational voice applications.
- **Alternatives considered:** ElevenLabs, Google Cloud Text-to-Speech, local ONNX models.
- **Trade-offs:** External API costs, but delivers realistic voice intonation with low latency.

### PydanticAI
- **Why chosen:** Type-safe agent framework with structured validation, system prompt configuration, and tool execution support.
- **Alternatives considered:** LangChain, AutoGen.
- **Trade-offs:** Schema validation overhead, providing structured runtime guarantees.

---

# Key Modules

### 1. `core/pipeline.py` ([`StreamingPipeline`](file:///c:/Users/vishn/PROJECT/voice-agent/core/pipeline.py#L82))
- **Responsibility:** Orchestrates turn-by-turn processing from transcribing incoming audio to streaming text generation and audio synthesis.
- **Inputs:** `WAV bytes`, `BotAgent`, `Transport`, `STTProvider`, `TTSProvider`.
- **Outputs:** `TurnResult` telemetry (STT ms, LLM TTFT, TTS TTFA, Total Turn ms).
- **Extension Points:** Callback hooks (`PipelineCallbacks`) for forwarding transcripts and status events to user interfaces.

### 2. `core/browser_transport.py` ([`BrowserTransport`](file:///c:/Users/vishn/PROJECT/voice-agent/core/browser_transport.py#L11))
- **Responsibility:** Manages full-duplex WebSocket audio buffer, framing Int16 PCM samples, and calculating energy RMS for VAD.
- **Inputs:** Base64-encoded PCM socket messages from client.
- **Outputs:** Formatted single-utterance `WAV` byte buffers.
- **Dependencies:** `numpy`, `wave`, `asyncio.Queue`.

### 3. `providers/` (`base.py`, `groq.py`, `cartesia.py`, `jina.py`)
- **Responsibility:** Provider abstractions enforcing interface contracts (`STTProvider`, `TTSProvider`, `EmbeddingProvider`).
- **Inputs/Outputs:** Standardized text/audio payload formats defined in [`providers/base.py`](file:///c:/Users/vishn/PROJECT/voice-agent/providers/base.py).
- **Extension Points:** Support for additional speech or text providers by implementing abstract base classes.

---

# Database & APIs

### Schema Overview (Postgres + `pgvector`)
The optional database schema (`db/schema.sql` / `pgvector`) persists vector document chunks for domain knowledge lookup.

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_id VARCHAR(50) NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1024), -- Jina AI v5 embedding dimension
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ON document_chunks USING ivfflat (embedding vector_cosine_ops);
```

### WebSocket Interface (`/ws`)
- **Connect:** `ws://localhost:8000/ws`
- **Incoming Messages:**
  - `{"type": "audio", "data": "<base64_pcm_int16>"}`
  - `{"type": "select_bot", "bot_id": "healthcare"}`
  - `{"type": "clear"}`
- **Outgoing Messages:**
  - `{"type": "status", "state": "listening" | "thinking" | "speaking"}`
  - `{"type": "user_transcript", "text": "..."}`
  - `{"type": "text_delta", "delta": "..."}`
  - `{"type": "audio", "data": "<base64_pcm_int16>"}`
  - `{"type": "turn_complete", "metrics": {...}}`

---

# Core Workflows

### Full Voice Conversation Turn
1. **User Speaks:** Browser captures audio via Web Audio API, streaming `Int16` base64 audio frames over the WebSocket connection.
2. **VAD Trigger:** `BrowserTransport` monitors frame energy. When energy drops below `silence_threshold` (200.0 RMS) for `silence_duration` (2.0s), reading completes.
3. **Transcribe:** `GroqSTTProvider` sends WAV to Groq API (`whisper-large-v3-turbo`), returning plain text.
4. **Context Injection:** `retrieve_context()` converts query text into vector representation via `JinaProvider` and fetches relevant chunks.
5. **Agent Inference & Sentence Streaming:** Selected `PydanticAI` bot receives context + query. Streaming response tokens enter `TextChunker`.
6. **Audio Synthesis:** Whenever `TextChunker` returns a full sentence or clause, it is dispatched to `CartesiaTTSProvider`. Synthesized audio streams to the client WebSocket for playout.

---

# Important Design Decisions

### 1. Sentence-Boundary Heuristic Chunking over Character Buffering
- **Problem:** Streaming LLM tokens directly to TTS token-by-token causes awkward pronunciation. Waiting for the entire LLM response introduces noticeable delay.
- **Chosen Solution:** Implemented [`TextChunker`](file:///c:/Users/vishn/PROJECT/voice-agent/core/pipeline.py#L8-L53) to parse LLM streams for sentence and clause pauses (`.`, `?`, `!`, `,`, `;`).
- **Why Chosen:** Balances natural speech intonation with reduced time-to-first-audio.
- **Trade-offs:** Clause chunks may synthesize before the full sentence context finishes generating.

### 2. Full-Duplex WebSockets over HTTP Polling
- **Problem:** Polling or standard unidirectional HTTP requests cannot support real-time audio streaming and cancellation signals.
- **Chosen Solution:** Unified persistent WebSocket connection passing JSON control frames and binary audio data.
- **Why Chosen:** Minimizes connection setup latency and enables continuous audio streaming.

---

# Challenges & Solutions

### Challenge 1: Micro-Stutter and Audio Discontinuity in Browser Playback
- **Problem:** Receiving non-uniform audio chunks over WebSockets caused audible gaps during playback.
- **Solution:** Implemented a Web Audio API queue buffer in the React frontend using `AudioContext` with scheduled sample playback.

### Challenge 2: Voice Activity Detection (VAD) Tuning Across Microphones
- **Problem:** Fixed energy RMS thresholds either cut off quiet speech or ran continuously on background noise.
- **Solution:** Combined RMS energy thresholding with minimum speech duration filters (`min_speech_duration = 0.3s`, `warmup_duration = 1.5s`) in [`BrowserTransport`](file:///c:/Users/vishn/PROJECT/voice-agent/core/browser_transport.py#L21-L38).

---

# Resume & Interview Notes

### Resume Bullets
- **Built a real-time voice agent application** in Python (FastAPI, WebSockets, AsyncIO) supporting interactive voice conversations with domain-specific AI agents.
- **Engineered an asynchronous streaming audio pipeline** integrating Groq Whisper STT, Groq Llama 3.3, and Cartesia Sonic TTS with sentence-boundary chunking algorithms.
- **Implemented voice activity detection (VAD)** using sliding-window RMS energy calculations over raw PCM streams to handle speech start and silence boundaries.
- **Integrated vector retrieval (RAG)** using Jina AI embeddings and `pgvector` to inject domain knowledge context into LLM agent prompts.

### STAR Summary
- **Situation:** Batch voice processing architectures introduce high multi-second delays per turn.
- **Task:** Build a functional streaming voice application for domain-specific assistant interactions.
- **Action:** Developed an asynchronous pipeline in FastAPI utilizing WebSockets, heuristic clause-based text chunking, and low-latency cloud providers (Groq and Cartesia).
- **Result:** Created a responsive full-duplex voice application capable of starting speech playback promptly after user input finishes.

### Common Interview Q&A

**Q: How do you handle user barge-in (interrupting the bot while it is speaking)?**
*A:* When the server VAD detects new speech input from the client while audio is playing, a cancellation event ([`_cancel_event`](file:///c:/Users/vishn/PROJECT/voice-agent/core/pipeline.py#L96)) is triggered. This stops ongoing LLM text generation, cancels pending TTS requests, and sends a `clear` status to reset the browser playback queue.

**Q: Why use sentence chunking instead of sending every token to TTS?**
*A:* Speech synthesis models require clause or sentence context (punctuation, phrasing) to produce natural cadence. Sending individual tokens results in disjointed audio, whereas buffering full clauses maintains audio quality while preserving low latency.

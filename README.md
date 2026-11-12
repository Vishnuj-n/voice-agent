# Real-Time Voice AI Agent

A modular, low-latency, full-duplex voice AI agent architecture built with **FastAPI**, **PydanticAI**, **React 19**, and **WebSockets**. Features domain-specific knowledge bots (Healthcare, Travel, Finance/Insurance, Legal, and Jira) with streaming speech-to-text (STT), text-to-speech (TTS), and pgvector-backed Retrieval-Augmented Generation (RAG).

---

## Architecture Overview

```
                     ┌───────────────────────────────────────────────┐
                     │          Browser / React 19 Frontend          │
                     │   (AudioWorklet PCM Capture & Streaming)      │
                     └───────────────────────▲───────────────────────┘
                                             │ WebSocket
                                             ▼
                     ┌───────────────────────────────────────────────┐
                     │              FastAPI Backend                  │
                     │          (core/browser_transport.py)          │
                     └───────────────────────▲───────────────────────┘
                                             │
                                  Streaming Pipeline
                                             │
      ┌────────────────────┬─────────────────┴──────────────────┬────────────────────┐
      ▼                    ▼                                    ▼                    ▼
┌───────────┐      ┌───────────────┐                    ┌───────────────┐     ┌─────────────┐
│    STT    │      │  PydanticAI   │                    │     RAG /     │     │     TTS     │
│   (Groq   │─────▶│ Domain Agents │◀──────────────────▶│   pgvector    │────▶│  (Cartesia  │
│  Whisper) │      │  (Llama 3.3)  │  (Jina Embeddings) │  PostgreSQL   │     │ Sonic 3.5)  │
└───────────┘      └───────────────┘                    └───────────────┘     └─────────────┘
```

### Key Highlights
- **End-to-End Low Latency:** Sub-second streaming audio pipeline with token-to-audio pipelining.
- **Pluggable Adapter Architecture:** Clear abstractions for `STTProvider`, `TTSProvider`, `LLMProvider`, `EmbeddingProvider`, and `Transport`.
- **Specialized Multi-Domain Bots:**
  - 🩺 **Healthcare:** Triage and guidance with strict non-diagnostic and emergency guardrails (Prompt-only).
  - ✈️ **Travel:** Flight search and booking assistant using dynamic function/tool calls.
  - 💳 **Finance & Insurance:** Product, policy terms, and premium guidance grounded via RAG over policy documents.
  - ⚖️ **Legal:** Legal reference information with automatic disclaimers grounded via RAG.
  - 📋 **Jira:** Issue tracking, project status, and task management integration.
- **Observability Built-in:** Persists turns and captures timing telemetry (`stt_ms`, `llm_time_to_first_token_ms`, `tts_time_to_first_audio_ms`, `total_ms`).
- **Flexible Transports:** Run either locally directly from the CLI (microphone & speaker loop) or over WebSockets via the React web UI.

---

## Tech Stack

- **Backend:** Python 3.13+, FastAPI, Uvicorn, WebSockets, PydanticAI, SQLAlchemy, Psycopg 3
- **Frontend:** React 19, TypeScript, Vite, Web Audio API / AudioWorklet
- **AI & Voice Services:**
  - **STT:** Groq Whisper (`whisper-large-v3-turbo`)
  - **LLM:** Groq Llama 3.3 70B (`llama-3.3-70b-versatile`)
  - **TTS:** Cartesia Sonic 3.5 (`sonic-3.5`)
  - **Embeddings:** Jina AI (`jina-embeddings-v5-text-small`) or OpenAI (`text-embedding-3-small`)
- **Database:** PostgreSQL with `pgvector`

---

## Directory Structure

```
voice-agent/
├── backend/                  # FastAPI app and WebSocket server
│   ├── api.py               # REST & WebSocket endpoints (/ws, /health, /bots, /sessions)
│   └── run.py               # Uvicorn entrypoint
├── bots/                     # Domain-specific PydanticAI bots
│   ├── healthcare.py        # Triage and medical guardrails bot
│   ├── travel.py            # Tool-calling flight/travel assistant
│   ├── finance.py           # Finance & insurance RAG bot
│   ├── legal.py             # Legal guidance RAG bot
│   └── jira.py              # Jira integration bot
├── core/                     # Core voice pipeline abstractions
│   ├── pipeline.py          # Streaming audio-to-text-to-speech engine
│   ├── transport.py         # Local sounddevice microphone/speaker transport
│   ├── browser_transport.py # Full-duplex WebSocket browser transport
│   ├── retrieval.py         # Vector similarity search over pgvector
│   └── ingestion.py         # Document chunking and embedding ingestion
├── db/                       # Database session & models
│   └── session.py           # SQLAlchemy & pgvector session management
├── frontend/                 # React 19 + TypeScript + Vite UI
│   ├── src/                 # Audio visualizers, bot selector, session controls
│   └── public/              # AudioWorklet processor for raw PCM streams
├── providers/                # Pluggable provider adapters
│   ├── base.py              # Base abstract classes for providers
│   ├── groq.py              # Groq STT & LLM adapters
│   ├── cartesia.py          # Cartesia streaming TTS adapter
│   ├── jina.py              # Jina AI embeddings adapter
│   └── openai.py            # OpenAI embeddings adapter
├── scripts/                  # Utility scripts (database seeding, benchmarks)
│   ├── seed_data.py         # Seed demo knowledge base into pgvector
│   ├── benchmark.py         # Latency benchmarking suite
│   └── test_*.py            # Standalone provider test scripts
├── docker-compose.yaml       # PostgreSQL + pgvector container
└── main.py                   # Local CLI voice-loop entrypoint
```

---

## Getting Started

### 1. Prerequisites

- Python 3.13 or higher (managed via `uv` or `pyenv`/`venv`)
- Node.js 18+ and `npm`
- Docker & Docker Compose (for PostgreSQL + pgvector)
- API Keys:
  - [Groq API Key](https://console.groq.com/)
  - [Cartesia API Key](https://play.cartesia.ai/)
  - [Jina AI API Key](https://jina.ai/?sui=apikey) (or OpenAI API key for embeddings)

---

### 2. Environment Configuration

Copy the example environment file and fill in your API credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```env
# Database
DATABASE_URL=postgresql://postgres:password@localhost:5432/voice_agent

# Groq (LLM & STT)
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_LLM_MODEL=llama-3.3-70b-versatile
GROQ_STT_MODEL=whisper-large-v3-turbo

# Cartesia (Streaming TTS)
CARTESIA_API_KEY=sk_car_your_cartesia_api_key_here
CARTESIA_VOICE_ID=db6b0ed5-d5d3-463d-ae85-518a07d3c2b4
CARTESIA_MODEL_ID=sonic-3.5

# Jina AI (Embeddings for RAG)
JINA_API_KEY=jina_your_jina_api_key_here
JINA_EMBEDDING_MODEL=jina-embeddings-v5-text-small

# Bot & Web Origin
DEFAULT_BOT=healthcare
WEB_ORIGIN=http://localhost:5173
```

---

### 3. Database Setup

Start the PostgreSQL service with `pgvector` support:

```bash
docker compose up -d
```

Seed the knowledge base (Finance and Legal sample documents):

```bash
# Using uv:
uv run python scripts/seed_data.py

# Or within an activated virtual environment:
python scripts/seed_data.py
```

---

### 4. Running the Application

#### Option A: Web Interface (Recommended)

1. **Start the Backend API Server:**
   ```bash
   uv run uvicorn backend.api:app --reload --port 8000
   ```

2. **Start the Frontend UI:**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Open [http://localhost:5173](http://localhost:5173) in your browser to interact with the voice agents.

#### Option B: Local CLI Voice Loop

Test the voice pipeline directly from your terminal using your local microphone and speakers:

```bash
# Healthcare bot (default)
uv run python main.py

# Or select a specific bot
uv run python main.py --bot travel
uv run python main.py --bot finance
uv run python main.py --bot legal
uv run python main.py --bot jira
```

Say *"bot stop"*, *"bot quit"*, or *"goodbye"* to end the session.

---

## Testing & Benchmarks

Run provider and pipeline benchmarks to evaluate round-trip audio and first-token latencies:

```bash
# Test Cartesia TTS streaming latency
uv run python scripts/test_cartesia_tts.py

# Test Groq STT transcription
uv run python scripts/test_groq_stt.py

# Run latency benchmark suite
uv run python scripts/benchmark.py
```

---

## License

This project is licensed under the MIT License.


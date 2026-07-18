# Sprint 3.5 — Browser Demo

## Goal
Build a minimal browser-based demo showcasing the completed Sprint 3 Streaming Pipeline. This sprint is demonstration-only and must not replace or modify the existing architecture. The objective is to let anyone open a browser, talk to the Healthcare agent, and understand the modular design. Keep implementation small, clean, and future-proof.

## Core Principles
Reuse the existing StreamingPipeline, providers, and Healthcare agent. Do not duplicate business logic or rewrite providers. Only add a browser transport and a web layer. Prefer architectural correctness over shortcuts while minimizing code.

## Existing Architecture (Do Not Modify)
StreamingPipeline, Transport abstraction, STT Provider, LLM Agent, TTS Provider, Provider Registry, Healthcare Agent, Provider interfaces, CLI workflow. Sprint 3.5 should only extend the project.

## Architecture
```
Browser (React + Vite)
    ↕ WebSocket (JSON control + binary audio)
FastAPI (backend/api.py)
    ↕
BrowserTransport (core/browser_transport.py — implements Transport ABC)
    ↕
StreamingPipeline (core/pipeline.py — untouched)
    ↕
STT (Groq) → LLM (Groq/PydanticAI) → TTS (Cartesia)
```

## Backend
Use FastAPI. Expose the existing StreamingPipeline over WebSockets. Do not create another pipeline. Implement BrowserTransport that receives browser microphone audio, feeds it into the existing STT, receives streamed TTS audio, streams audio chunks back to the browser, and exposes the metrics already produced by the backend. The CLI transport must continue working unchanged.

## Communication
Use WebSockets from day one. Do not use polling. Support client→audio chunks, server→partial transcripts, assistant text, streamed audio chunks, latency metrics, connection status, and errors. Design the protocol so future bots require no protocol changes.

## Frontend
Use React + Vite. Single-page application with no routing, authentication, database, settings page, or conversation persistence. Refreshing the page resets the conversation. API endpoint must come from `VITE_API_URL`; never hardcode URLs.

## UI
Create two tabs: **Voice Agent** and **Architecture**.

### Voice Agent
Display four bots:
- ✅ Healthcare (enabled)
- ⏳ Travel (disabled)
- ⏳ Finance (disabled)
- ⏳ Legal (disabled)

Disabled bots should be greyed out with tooltip: **"Available in Sprint 4"**.

Include:
- Conversation area with simple user/assistant chat bubbles (no markdown, timestamps, or history beyond the current session)
- 🎤 Start Listening / ⏹ Stop Listening buttons
- Browser microphone permission request
- Automatic recording, transcription, response generation, TTS, and playback after pressing Start
- Connection state: Connected, Listening, Thinking, Speaking, Disconnected
- Metrics panel showing existing backend metrics (STT, LLM, TTFT, TTS, TTFA, Total)

### Architecture Tab
A simple static page highlighting:
- Modular Providers (Transport, STT, LLM, TTS, Provider Registry)
- Streaming Pipeline (Browser → STT → LLM → Streaming TTS → Browser)
- Benefits: Modular, Streaming, Concurrent Processing, Low Latency, Provider Swapping
- Current Features: Healthcare Bot, Streaming Voice Pipeline, Browser Transport, WebSockets, Live Metrics
- Planned Features: Travel Bot, Finance Bot, Legal Bot, RAG, pgvector, Persistent Conversations

## Audio
Browser microphone → BrowserTransport → existing StreamingPipeline → streamed audio back over WebSocket → browser speaker. Audio playback should begin automatically as chunks arrive without waiting for the full response.

## WebSocket Protocol

### Client → Server
| Message | Format | Description |
|---------|--------|-------------|
| `start_listening` | `{"type": "start_listening"}` | Begin recording |
| `stop_listening` | `{"type": "stop_listening"}` | End recording, trigger STT + pipeline |
| `audio_chunk` | `{"type": "audio_chunk", "data": "<base64>"}` | Raw PCM Int16 audio chunk |
| `select_bot` | `{"type": "select_bot", "bot": "healthcare"}` | Bot selection |

### Server → Client
| Message | Format | Description |
|---------|--------|-------------|
| `status` | `{"type": "status", "state": "connected\|listening\|thinking\|speaking\|disconnected"}` | Connection state |
| `bots` | `{"type": "bots", "bots": [...]}` | Available bots list |
| `transcript` | `{"type": "transcript", "text": "...", "speaker": "user"}` | User transcript |
| `response_text` | `{"type": "response_text", "text": "..."}` | Assistant text delta |
| `audio_start` | `{"type": "audio_start", "format": {...}}` | Audio stream header |
| `audio_chunk` | `{"type": "audio_chunk", "data": "<base64>"}` | TTS audio chunk |
| `audio_end` | `{"type": "audio_end"}` | Audio stream complete |
| `metrics` | `{"type": "metrics", "stt_ms": N, ...}` | Timing metrics |
| `error` | `{"type": "error", "message": "..."}` | Error |

## Implementation Steps

### Phase 1: Backend
1. Create `backend/` directory with `api.py` (FastAPI + WebSocket endpoint)
2. Create `core/browser_transport.py` (BrowserTransport implementing Transport ABC)
3. Create `backend/run.py` (uvicorn entry point)
4. Create `backend/requirements.txt`

### Phase 2: Frontend
1. Scaffold Vite + React + TypeScript project in `frontend/`
2. Create WebSocket hook (`useWebSocket.ts`)
3. Create audio hook (`useAudio.ts` — mic capture + playback)
4. Create components: VoiceAgent, Architecture, BotCard, MetricsPanel, StatusBar
5. Create App.tsx with tab layout
6. Style with minimal CSS

### Phase 3: Deployment
1. Verify `render.yaml` paths
2. Update `.gitignore`

## File Targets

| File | Action | Purpose |
|------|--------|---------|
| `backend/api.py` | Create | FastAPI app + WebSocket endpoint |
| `backend/run.py` | Create | Uvicorn entry point |
| `backend/requirements.txt` | Create | Backend dependencies |
| `core/browser_transport.py` | Create | BrowserTransport (Transport ABC impl) |
| `frontend/` | Create (scaffold) | Vite + React + TypeScript |
| `frontend/src/App.tsx` | Create | Tab layout |
| `frontend/src/hooks/useWebSocket.ts` | Create | WebSocket hook |
| `frontend/src/hooks/useAudio.ts` | Create | Mic capture + playback |
| `frontend/src/components/VoiceAgent.tsx` | Create | Voice Agent tab |
| `frontend/src/components/Architecture.tsx` | Create | Architecture tab |
| `frontend/src/components/BotCard.tsx` | Create | Bot card |
| `frontend/src/components/MetricsPanel.tsx` | Create | Metrics display |
| `frontend/src/components/StatusBar.tsx` | Create | Status indicator |
| `frontend/src/main.tsx` | Create | Entry point |
| `frontend/src/index.css` | Create | Styles |
| `frontend/vite.config.ts` | Edit | Proxy config |
| `frontend/.env.example` | Create | VITE_API_URL |
| `.gitignore` | Edit | Add frontend ignores |

**Existing files NOT modified:** `core/pipeline.py`, `core/transport.py`, `providers/`, `bots/`, `main.py`, `config.py`

## Verification Steps
1. Backend starts: `cd backend && uv run uvicorn api:app --host 0.0.0.0 --port 8000`
2. Health check: `curl http://localhost:8000/health`
3. WebSocket connects in browser
4. Mic capture works (permission prompt → status change)
5. STT works (transcript appears)
6. LLM streams (response text appears incrementally)
7. TTS plays (audio through browser speakers)
8. Metrics display (all 5 metrics)
9. CLI unchanged (`uv run main.py` still works)
10. Frontend builds (`cd frontend && npm run build`)
11. Disabled bots greyed out with tooltip

## DONE PART 

All files created. Here's what was implemented:

**Backend (3 files):**
- `core/browser_transport.py` — `BrowserTransport` implementing `Transport` ABC. Sends TTS audio over WebSocket instead of to a speaker. Buffers browser mic audio into WAV for STT.
- `backend/api.py` — FastAPI app with `/health` endpoint and `/ws` WebSocket endpoint. Handles the full protocol: bot selection, audio streaming, STT, LLM streaming, TTS streaming, metrics.
- `backend/run.py` — Uvicorn entry point.

**Frontend (10 files):**
- `frontend/src/hooks/useWebSocket.ts` — WebSocket connection, message handling, audio playback via AudioContext
- `frontend/src/hooks/useAudio.ts` — Mic capture via ScriptProcessorNode, Float32→Int16 conversion
- `frontend/src/components/VoiceAgent.tsx` — Main tab with bot selector, chat bubbles, start/stop, status, metrics
- `frontend/src/components/Architecture.tsx` — Static architecture info page
- `frontend/src/components/BotCard.tsx` — Bot card with enabled/disabled states
- `frontend/src/components/MetricsPanel.tsx` — Latency metrics display
- `frontend/src/components/StatusBar.tsx` — Connection state indicator
- `frontend/src/App.tsx` — Tab layout
- `frontend/src/index.css` — Dark theme styling
- Config files: `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `.env.example`

**Existing files untouched:** `core/pipeline.py`, `core/transport.py`, `providers/`, `bots/`, `main.py`, `config.py`

**Updated:** `pyproject.toml` (added fastapi, uvicorn, websockets deps), `.gitignore` (added frontend ignores)

To run:
```bash
# Backend
cd backend && uv run uvicorn api:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend && npm install && npm run dev
```
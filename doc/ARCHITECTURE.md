# Architecture

Status: Draft v1 (derived from Architecture & Design Report, Rev. 2)

---

## 1. Overview

A single Python process running a modular, voice-driven AI agent system with
four domain-specific bots (Healthcare, Travel, Finance/Insurance, Legal). V1
is a fully functional local voice loop (mic in, speaker out). Every external
dependency is reached through an adapter interface so that a future move to
telephony (Twilio) or a different STT/LLM/TTS/embedding vendor requires a new
adapter class and a config change — not a rewrite of the core pipeline.

Bots are pluggable modules within one process, not microservices.

---

## 2. Adapter Architecture

Five abstract interfaces, each with a registry and config-string-driven
selection. No core pipeline code imports a vendor SDK directly.

| Adapter | Purpose | v1 Implementation |
|---|---|---|
| `Transport` | Audio in/out | Local mic/speaker script |
| `STTProvider` | Speech → text | Groq Whisper (`whisper-large-v3-turbo`), non-streaming |
| `LLMProvider` | Reasoning / generation | Groq (Llama 3.3 70B or similar), via PydanticAI, streaming |
| `TTSProvider` | Text → speech | Cartesia (default), streaming |
| `EmbeddingProvider` | Text → vector | OpenAI `text-embedding-3-small` |

Swapping any one implementation should require only a config change plus one
new adapter class.

---

## 3. Request Flow (Local Voice Loop, v1)

```
 Mic (Transport)
     │
     ▼
 record_until_silence()  ── energy-based VAD (v1; may need Silero/WebRTC VAD later)
     │
     ▼
 STTProvider.transcribe()  ── Groq Whisper, non-streaming (turn already VAD-delimited)
     │
     ▼
 Bot Agent (PydanticAI)
     │  ├─ Healthcare: prompt-only, no RAG, no tools
     │  ├─ Travel: @agent.tool search_flights() (mocked) — tool-decision pass
     │  │           is awaited in full, post-tool response pass streams
     │  ├─ Finance: RAG via direct psycopg + pgvector query over finance_docs
     │  └─ Legal:   RAG via direct psycopg + pgvector query over legal_docs
     │
     ▼
 LLMProvider (Groq, streaming)  ── output streamed in sentence/clause chunks
     │
     ▼
 TTSProvider (Cartesia, streaming)  ── fed incrementally so playback starts
     │                                  before full response is generated
     ▼
 Speaker (Transport)
```

In parallel: every stage duration and first-output marker is captured and
written to the `turns` table (see `schema.md`).

---

## 4. Orchestration

- Implemented with **PydanticAI**. LangChain is explicitly excluded.
- Each bot is a single PydanticAI `Agent`:
  - System prompt tailored to the domain
  - Plain-string output type (voice output — no structured/JSON output)
  - Zero or more `@agent.tool` functions (Travel only, for v1)
- RAG retrieval (Finance, Legal) is implemented as **direct `psycopg` queries**
  against pgvector. No retrieval framework (e.g. LlamaIndex, LangChain
  retrievers) is used.
- Bot selection per session is manual/config-driven (e.g. a CLI `--bot` flag).
  Automated routing (IVR, phone-number-per-bot, intent detection) is
  explicitly out of scope for v1.

---

## 5. Domain Bots

| Bot | Knowledge strategy | Key constraint |
|---|---|---|
| Healthcare | Prompt-only, no RAG | Must never diagnose or suggest medication; redirects urgent issues to emergency services; strict guardrails |
| Travel | Tool-calling, no static knowledge | Calls mocked `search_flights` tool; designed for future real provider (Amadeus, Duffel, Skyscanner) |
| Finance/Insurance | RAG over policy/product documents | Retrieval must ground specific coverage terms/premiums/limits — never generated from general model knowledge |
| Legal | RAG over legal reference documents | Always includes a "general information, not legal advice" disclaimer |

Each bot is a self-contained module in the single process — not a separate
microservice.

---

## 6. Streaming Behavior

- LLM output streams and is fed to TTS incrementally so audio playback can
  begin before the full response is generated.
- **Exception — Travel bot:** the tool-decision LLM pass must be awaited in
  full (function-call objects can't stream). The post-tool-result response
  pass streams normally. Healthcare, Finance, and Legal have no such split.

---

## 7. Observability

Every turn logs both full-stage durations and streaming-specific
first-output markers (see `schema.md` for the exact `turns` fields). These
must be queryable directly via SQL (e.g. "turns where `retrieval_ms` > 500")
without a separate observability stack.

---

## 8. Failure Handling

- Any mid-call failure — API timeout, empty/irrelevant retrieval,
  unrecognized request, empty STT output — triggers a short scripted
  fallback line rather than dead air or a crash.
- Every fallback occurrence is logged on the same turn record
  (`was_fallback`, `error`).

---

## 9. Twilio Readiness (Design Only — Not Built in v1)

- `Transport` is the seam for a future `TwilioTransport`, implementing
  `connect / receive_audio_chunks / send_audio / close` over Twilio's Media
  Streams websocket.
- Twilio's 8kHz μ-law, ~20ms-frame audio format (vs. local mic's 16kHz+
  audio) is handled entirely inside `TwilioTransport` when built — no other
  component changes.
- Known risk: STT tuned only on clean local mic audio may degrade on
  Twilio's 8kHz μ-law phone audio.

---

## 10. Non-Functional Requirements

- **Latency:** 1–2 seconds end-to-end per turn (caller stops talking → bot
  starts responding).
- **Cost:** Provider selections (Groq, Cartesia, OpenAI embeddings, single
  Postgres instance) kept deliberately lean — no redundant infrastructure.
- **Language:** English-only for v1; STT/TTS adapters keep the architecture
  language-pluggable (Sarvam designed for, not built).
- **Runtime:** Single Python process.

---

## 11. Explicit Non-Goals for v1

- Twilio or any telephony integration itself (only the seam is designed).
- Real bot-routing logic for phone calls.
- Hindi or other regional-language support.
- A real flight/hotel search API.
- Mid-conversation hand-off between bots.
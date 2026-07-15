
**Status:** Draft v1 (derived from Architecture & Design Report, Rev. 2)

---
## 1. Summary

A modular, voice-driven AI agent system offering four domain-specific knowledge bots — Healthcare, Travel, Finance/Insurance, and Legal. V1 ships as a fully functional local voice loop (microphone in, speaker out) and is architected so that adding telephony (Twilio or otherwise) later requires only a new adapter, not a rewrite.

## 2. Problem Statement

Teams building voice AI agents typically couple their pipeline tightly to a specific STT/LLM/TTS vendor stack and a specific transport (e.g., telephony), making later vendor swaps or channel additions costly. This product needs to prove out voice-agent UX and multi-domain knowledge handling today, on a local mic/speaker loop, while guaranteeing that a future move to phone-based delivery (Twilio) doesn't require re-architecting the core system.

## 3. Goals

- Ship a working, testable local voice agent across four domains.
- Keep end-to-end response latency in the **1–2 second** range per turn.
- Keep the system **cheap** to run (provider choices, single Postgres instance, no unnecessary infrastructure).
- Make every external dependency (audio transport, STT, LLM, TTS, embeddings) swappable via a one-line config change plus one new adapter class.
- Support **English only** in v1, without foreclosing future languages.

## 4. Non-Goals (Out of Scope for v1)

- Twilio or any telephony integration itself (only the integration seam is designed for it).
- Real bot-routing logic for phone calls (IVR/DTMF menu, phone-number-per-bot, intent-based routing).
- Hindi or other regional-language support (Sarvam STT/TTS is designed for, not built).
- A real flight/hotel search API for the Travel bot.
- Mid-conversation hand-off between bots (each session is scoped to one bot).

## 5. Users & Use Cases

| User                                                     | Use case                                                                                                                  |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Caller seeking healthcare triage/scheduling/general info | Talks to the Healthcare bot; gets safe, non-diagnostic guidance and is redirected to emergency services if urgent.        |
| Caller planning travel                                   | Talks to the Travel bot; gets live-style flight availability via a tool call.                                             |
| Caller with insurance/finance questions                  | Talks to the Finance bot; gets answers grounded in real policy/product documents via RAG.                                 |
| Caller with legal questions                              | Talks to the Legal bot; gets answers grounded in legal reference documents via RAG, with a "not legal advice" disclaimer. |
| Internal QA/analyst                                      | Reviews persisted transcripts and per-turn latency data in Postgres to debug bad responses or slow turns.                 |

## 6. Functional Requirements

### 6.1 Adapter Architecture

- The system **must** define five abstract adapter interfaces, each with a registry and config-string-driven selection: `Transport`, `STTProvider`, `LLMProvider`, `TTSProvider`, `EmbeddingProvider`.
- No core pipeline code may import a vendor SDK directly — all vendor access goes through an adapter.
- Swapping any one adapter's implementation must require only a config change plus one new class, not changes to the core pipeline.

### 6.2 Interaction Surface (v1)

- The system **must** support a real local voice loop: real microphone capture, real speaker playback, real STT and TTS (no text-only stub).
- Audio capture is implemented as a plain local script, behind the `Transport` interface, so it can later be replaced by a `TwilioTransport` without touching the rest of the system.

### 6.3 Knowledge Domains

The system **must** support exactly four domain bots, each a self-contained module in a single process (not a separate microservice):

|Bot|Knowledge strategy|Requirement detail|
|---|---|---|
|Healthcare|Prompt-only, no RAG|Must never diagnose or suggest medication; must redirect urgent issues to emergency services; strict guardrails required.|
|Travel|Tool-calling, no static knowledge|Must call a `search_flights` tool (mocked for v1, designed to be replaced by a real provider such as Amadeus, Duffel, or Skyscanner).|
|Finance/Insurance|RAG over real policy/product documents|Retrieval must ground specific coverage terms, premiums, and limits — not be generated from general model knowledge.|
|Legal|RAG over real legal reference documents|Must always include a "general information, not legal advice" disclaimer.|

- Bot selection for a session is manual/config-driven for v1 (e.g., a CLI flag). Automated routing (IVR, phone-number-per-bot, intent detection) is explicitly deferred.

### 6.4 Orchestration

- Agent orchestration and tool calling **must** be implemented with PydanticAI (LangChain is explicitly excluded from the design).
- Each bot is a single PydanticAI `Agent` with a system prompt, a plain-string output type (voice output), and, where applicable, one or more `@agent.tool` functions.
- RAG retrieval (Finance, Legal) **must** be implemented as direct `psycopg` queries against pgvector — no retrieval framework.

### 6.5 Provider Stack

| Role         | Provider                                               | Streaming                                     |
| ------------ | ------------------------------------------------------ | --------------------------------------------- |
| LLM          | Groq (Llama 3.3 70B or similar), via PydanticAI        | Streaming required                            |
| STT          | Groq Whisper (`whisper-large-v3-turbo`)                | Non-streaming (turn is already VAD-delimited) |
| TTS          | Cartesia (default); Sarvam supported later             | Streaming required                            |
| Embeddings   | OpenAI `text-embedding-3-small`                        | N/A                                           |
| Vector store | pgvector, in the same Postgres instance as transcripts | N/A                                           |

- LLM output **must** stream and be fed to TTS incrementally (sentence/clause chunks) so audio playback can begin before the full response is generated.
- For the Travel bot specifically, the tool-decision LLM pass **must** be awaited in full (function-call objects can't stream), while the post-tool-result response pass streams normally. Healthcare, Finance, and Legal have no such split.

### 6.6 Persistence & Data Model

- The system **must** persist call sessions and per-turn data to Postgres.
- `call_sessions`: `id`, `bot_name`, `started_at`, `ended_at`.
- `turns`: `id`, `session_id`, `turn_index`, `caller_text`, `bot_text`, `stt_ms`, `retrieval_ms`, `llm_total_ms`, `llm_time_to_first_token_ms`, `tts_total_ms`, `tts_time_to_first_audio_ms`, `total_ms`, `was_fallback`, `error`, `created_at`.
- pgvector collections `finance_docs` and `legal_docs` hold chunked, embedded source documents for retrieval.

### 6.7 Observability

- Every turn **must** log both full-stage durations (`stt_ms`, `retrieval_ms`, `llm_total_ms`, `tts_total_ms`, `total_ms`) and streaming-specific first-output markers (`llm_time_to_first_token_ms`, `tts_time_to_first_audio_ms`).
- These fields must be queryable (e.g., "show turns where retrieval took
    
    > 500ms") without a separate observability stack.
    

### 6.8 Failure Handling

- Any mid-call failure (API timeout, empty/irrelevant retrieval, unrecognized request, empty STT output) **must** trigger a short scripted fallback line rather than dead air or a crash.
- Every fallback occurrence **must** be logged on the same turn record, with the error captured, for later review.

### 6.9 Twilio Readiness (Design Only, Not Built)

- The `Transport` abstraction is the defined seam for a future `TwilioTransport`, implementing `connect / receive_audio_chunks / send_audio / close` over Twilio's Media Streams websocket.
- Handling of Twilio's 8kHz μ-law, ~20ms-frame audio format (vs. local mic's 16kHz+ audio) is isolated entirely inside `TwilioTransport` when built; no other component needs to change.

## 7. Non-Functional Requirements

- **Latency:** 1–2 seconds end-to-end per turn (caller stops talking → bot starts responding).
- **Cost:** Provider selections (Groq, Cartesia, OpenAI embeddings, single Postgres instance) must keep run cost low; no redundant infrastructure.
- **Language:** English-only for v1; architecture must remain language-pluggable via the STT/TTS adapters.
- **Runtime:** Single Python process; bots are pluggable modules, not microservices.

## 8. System Architecture (Reference)
![[Pasted image 20260714130629.png]]
## 9. Success Metrics

- 90%+ of turns fall within the 1–2s end-to-end latency target across all four bots.
- Time-to-first-token and time-to-first-audio are consistently a small fraction of total stage duration (validating that streaming is actually reducing perceived latency).
- Zero unhandled crashes during a test call — all failures degrade to the scripted fallback line.
- Healthcare bot passes adversarial guardrail testing (no diagnosis/ medication advice leakage) before any real-caller use.
- Finance/Legal RAG answers are traceable to source documents in `finance_docs`/`legal_docs`.

## 10. Risks & Open Questions

- **VAD sophistication:** a simple energy-based approach is the v1 plan; may need a dedicated model (Silero, WebRTC VAD) if false cut-offs occur in testing.
- **Real document sourcing:** Finance/Legal RAG quality depends on replacing placeholder sample content with real policy/legal documents.
- **Real Travel API:** the`search_flights` tool needs a real provider integration (Amadeus, Duffel, Skyscanner, or similar) before production use.
- **Phone-audio quality gap:** STT tuned only on clean local mic audio may degrade on Twilio's 8kHz μ-law phone audio; this is deferred to `TwilioTransport` work but flagged as a known future risk.
- **Bot routing mechanism:** the right approach (IVR menu, phone-number-per- bot, intent detection) depends on telephony provider capabilities and is intentionally undecided until that phase begins.

## 11. Milestones (Suggested, Not Yet Scheduled)

1. Core adapters (Transport/STT/LLM/TTS/Embedding) + registry scaffolding.
2. Local mic/speaker transport working end-to-end with one bot (e.g., Healthcare) as a walking skeleton.
3. Remaining three bots (Travel, Finance, Legal) implemented, including pgvector ingestion pipeline for Finance/Legal docs.
4. Latency logging and fallback handling wired into every turn.
5. Guardrail/adversarial testing pass for Healthcare.
6. (Post-v1) Twilio transport implementation and real bot routing.

## 13. Explicitly Deferred (Tracking Only)

|Item|Deferred to|
|---|---|
|Twilio telephony integration|Post-v1|
|Phone-call bot routing (IVR/DTMF/intent)|Post-v1, with Twilio|
|Hindi/regional-language support (Sarvam)|Future, if required|
|Real flight/hotel search API|Post-v1|
|Mid-conversation bot hand-off|Not currently planned|

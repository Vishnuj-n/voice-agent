# Voice Bot Internship Sprint Plan

Derived from: Architecture & Design Report, Rev. 2 (PRD v1)

---

## Sprint 0 – Setup [DONE]
- [X] Initialize project (`uv init`)
- [X] Add dependencies
- [X] Create `.env.example`
- [X] Create `config.py`
  - [X] Config model
  - [X] `load_config()`
  - [X] `get_provider_string()`
- [X] Create `db/session.py`
  - [X] `get_engine()`
  - [X] `init_db()`

---

## Sprint 1 – Real Calls First, Then Interfaces
Rationale: writing abstract interfaces before touching a real provider API means
guessing at a shape you don't understand yet. Do one real integration first,
then extract the interface from what you actually needed.

- [x] Direct provider calls (no interface yet)
  - [x] `GroqWhisperSTT` — one real transcription call against a sample audio file
  - [x] `CartesiaTTS` — one real synthesis call producing playable audio
- [x] `providers/base.py` (written *after* the above, based on what both calls needed)
  - [x] `STTProvider`
  - [x] `TTSProvider`
  - [x] `LLMProvider`
- [x] `providers/registry.py`
  - [x] `get_stt_provider()`
  - [x] `get_tts_provider()`
  - [x] `get_llm_provider()`

**Open decision to make explicitly (not silently skip):** `Transport` is one of
the five required adapters per the PRD (§6.1). Decide now whether its abstract
interface is deferred until Twilio work begins (reasonable — only one
implementation exists today) or whether a minimal `Transport` base class
belongs in `providers/base.py` alongside the others for consistency.

---

## Sprint 2 – Walking Skeleton
- [ ] `bots/healthcare.py` (PydanticAI `Agent`, string output, guardrail system prompt)
- [ ] `core/transport.py`
  - [ ] `record_until_silence()` (simple energy-based VAD for v1)
  - [ ] `play()`
- [ ] `main.py`
  - [ ] `run_one_turn()`
- [ ] **Rough timing check** — wrap each stage (`stt`, `llm`, `tts`) with
      `time.perf_counter()` and print durations to console. Not persisted yet
      (that's Sprint 5) — this is just an early sanity read on whether the
      1–2s latency target (PRD §7) is achievable before building three more
      bots on the same pipeline.

**Checkpoint:** Local Mic → STT → LLM → TTS → Speaker, with visible per-stage timing.

---

## Sprint 3 – Pipecat / Streaming Pipeline
- [ ] Create `core/pipeline.py`
- [ ] `build_pipeline()`
- [ ] `PydanticAIService`
- [ ] Replace `run_one_turn()` with pipeline
- [ ] Confirm LLM output streams into TTS incrementally (sentence/clause
      chunks) per PRD §6.5 — verify audio starts before full response is generated

---

## Sprint 4 – Remaining Bots
- [ ] `providers/base.py` — add `EmbeddingProvider` interface (PRD §6.1
      requires this as the fifth adapter; don't let OpenAI embeddings become
      an unwrapped vendor dependency baked into RAG ingestion)
- [ ] `OpenAIEmbeddings` (implements `EmbeddingProvider`)
- [ ] Vector Store
  - [ ] `similarity_search()` — direct `psycopg` + pgvector, no retrieval framework
- [ ] Ingestion
  - [ ] `chunk_document()`
  - [ ] `ingest_file()`
- [ ] Travel Bot
  - [ ] `search_flights()` tool (mocked, `@agent.tool`)
  - [ ] Verify tool-decision LLM pass is awaited in full (no streaming) while
        the post-tool-result pass streams normally (PRD §6.5)
- [ ] Finance Bot (RAG over `finance_docs`)
- [ ] Legal Bot (RAG over `legal_docs`, always includes "not legal advice" disclaimer)
- [ ] Bot Registry (config/CLI-driven selection, PRD §6.3)

---

## Sprint 5 – Database & Metrics
- [ ] `db/models.py` — `call_sessions`, `turns` (see `schema.md`)
- [ ] Add latency timers for all required fields (PRD §6.7):
      `stt_ms`, `retrieval_ms`, `llm_total_ms`, `llm_time_to_first_token_ms`,
      `tts_total_ms`, `tts_time_to_first_audio_ms`, `total_ms`
- [ ] Save turns to database
- [ ] Confirm fields are queryable ad hoc (e.g. "turns where retrieval > 500ms")

---

## Sprint 6 – Error Handling
- [ ] `core/fallback.py`
- [ ] `RecoverableError`
- [ ] `handle_turn_error()`
- [ ] Wire fallback into pipeline for: API timeout, empty/irrelevant retrieval,
      unrecognized request, empty STT output (PRD §6.8)
- [ ] Confirm every fallback occurrence logs `was_fallback` + `error` on the turn record

---

## Sprint 7 – Final Polish
- [ ] CLI (`--bot`)
- [ ] Test all 4 bots end-to-end
- [ ] Verify latency logging against success metrics (PRD §9): 90%+ turns in 1–2s
- [ ] Healthcare guardrail / adversarial testing (no diagnosis or medication advice leakage)
- [ ] Documentation & cleanup

---

## Explicitly Deferred (Post-v1, per PRD §13)
| Item | Deferred to |
|---|---|
| Twilio telephony integration | Post-v1 |
| Phone-call bot routing (IVR/DTMF/intent) | Post-v1, with Twilio |
| Hindi/regional-language support (Sarvam) | Future, if required |
| Real flight/hotel search API | Post-v1 |
| Mid-conversation bot hand-off | Not currently planned |
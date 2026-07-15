# Voice Bot Internship Sprint Plan

## Sprint 0 – Setup
- [ ] Initialize project (`uv init`)
- [ ] Add dependencies
- [ ] Create `.env.example`
- [ ] Create `config.py`
  - [ ] Config model
  - [ ] `load_config()`
  - [ ] `get_provider_string()`
- [ ] Create `db/session.py`
  - [ ] `get_engine()`
  - [ ] `init_db()`

---

## Sprint 1 – Provider Skeleton
- [ ] `providers/base.py`
  - [ ] STTProvider
  - [ ] TTSProvider
  - [ ] LLMProvider
- [ ] `providers/registry.py`
  - [ ] `get_stt_provider()`
  - [ ] `get_tts_provider()`

---

## Sprint 2 – Walking Skeleton
- [ ] `GroqWhisperSTT`
- [ ] `CartesiaTTS`
- [ ] `bots/healthcare.py`
- [ ] `core/transport.py`
  - [ ] `record_until_silence()`
  - [ ] `play()`
- [ ] `main.py`
  - [ ] `run_one_turn()`

**Checkpoint:** Local Mic → STT → LLM → TTS → Speaker

---

## Sprint 3 – Pipecat
- [ ] Create `core/pipeline.py`
- [ ] `build_pipeline()`
- [ ] `PydanticAIService`
- [ ] Replace `run_one_turn()` with pipeline

---

## Sprint 4 – Remaining Bots
- [ ] Travel Bot
  - [ ] `search_flights()`
- [ ] OpenAI Embeddings
- [ ] Vector Store
  - [ ] `similarity_search()`
- [ ] Ingestion
  - [ ] `chunk_document()`
  - [ ] `ingest_file()`
- [ ] Finance Bot
- [ ] Legal Bot
- [ ] Bot Registry

---

## Sprint 5 – Database & Metrics
- [ ] `db/models.py`
- [ ] Add latency timers
- [ ] Save turns to database

---

## Sprint 6 – Error Handling
- [ ] `core/fallback.py`
- [ ] `RecoverableError`
- [ ] `handle_turn_error()`
- [ ] Wire fallback into pipeline

---

## Sprint 7 – Final Polish
- [ ] CLI (`--bot`)
- [ ] Test all 4 bots
- [ ] Verify latency logging
- [ ] Healthcare guardrail testing
- [ ] Documentation & cleanup
# Data Model / Schema

Status: Draft v1 (derived from Architecture & Design Report, Rev. 2)

Single Postgres instance holds both transcript/session data and the
pgvector collections used for RAG. No separate vector database.

---

## 1. `call_sessions`

One row per session (one bot per session — no mid-conversation hand-off).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID / serial PK | |
| `bot_name` | text | One of `healthcare`, `travel`, `finance`, `legal` |
| `started_at` | timestamptz | |
| `ended_at` | timestamptz | Nullable until session closes |

```sql
CREATE TABLE call_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_name    TEXT NOT NULL,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at    TIMESTAMPTZ
);
```

---

## 2. `turns`

One row per conversational turn. Carries both caller/bot text and full
latency instrumentation (PRD §6.6, §6.7).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID / serial PK | |
| `session_id` | UUID FK → `call_sessions.id` | |
| `turn_index` | int | 0-based order within the session |
| `caller_text` | text | STT output |
| `bot_text` | text | Full generated response text |
| `stt_ms` | int | Full STT stage duration |
| `retrieval_ms` | int | RAG retrieval duration (Finance/Legal only; null otherwise) |
| `llm_total_ms` | int | Full LLM stage duration |
| `llm_time_to_first_token_ms` | int | Streaming first-token marker |
| `tts_total_ms` | int | Full TTS stage duration |
| `tts_time_to_first_audio_ms` | int | Streaming first-audio marker |
| `total_ms` | int | End-to-end turn duration |
| `was_fallback` | boolean | True if a scripted fallback line was used |
| `error` | text | Nullable; populated when `was_fallback` is true |
| `created_at` | timestamptz | |

```sql
CREATE TABLE turns (
    id                           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id                   UUID NOT NULL REFERENCES call_sessions(id),
    turn_index                   INT NOT NULL,
    caller_text                  TEXT,
    bot_text                     TEXT,
    stt_ms                       INT,
    retrieval_ms                 INT,
    llm_total_ms                 INT,
    llm_time_to_first_token_ms   INT,
    tts_total_ms                 INT,
    tts_time_to_first_audio_ms   INT,
    total_ms                     INT,
    was_fallback                 BOOLEAN NOT NULL DEFAULT false,
    error                        TEXT,
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_turns_session_id ON turns(session_id);
```

Example diagnostic query (PRD §6.7 — must be answerable without a separate
observability stack):

```sql
SELECT session_id, turn_index, retrieval_ms
FROM turns
WHERE retrieval_ms > 500
ORDER BY retrieval_ms DESC;
```

---

## 3. pgvector Collections

Two collections, same Postgres instance, used only by the Finance and Legal
bots for grounded retrieval (never used for Healthcare or Travel).

### 3.1 `finance_docs`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID / serial PK | |
| `source_document` | text | Filename or identifier of the source policy/product doc |
| `chunk_index` | int | Position of this chunk within the source document |
| `content` | text | Raw chunk text |
| `embedding` | vector(1536) | `text-embedding-3-small` output |
| `created_at` | timestamptz | |

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE finance_docs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_document  TEXT NOT NULL,
    chunk_index      INT NOT NULL,
    content          TEXT NOT NULL,
    embedding        VECTOR(1536) NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_finance_docs_embedding
    ON finance_docs USING ivfflat (embedding vector_cosine_ops);
```

### 3.2 `legal_docs`

Identical shape to `finance_docs`, separate table so retrieval never crosses
domains.

```sql
CREATE TABLE legal_docs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_document  TEXT NOT NULL,
    chunk_index      INT NOT NULL,
    content          TEXT NOT NULL,
    embedding        VECTOR(1536) NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_legal_docs_embedding
    ON legal_docs USING ivfflat (embedding vector_cosine_ops);
```

Retrieval (both collections) is a direct `psycopg` cosine-similarity query —
no retrieval framework:

```sql
SELECT content, source_document
FROM finance_docs
ORDER BY embedding <=> :query_embedding
LIMIT 5;
```

---

## 4. Open Questions (carried from PRD §10)

- Placeholder sample content in `finance_docs`/`legal_docs` needs to be
  replaced with real policy/legal documents before quality can be assessed.
- `ivfflat` index parameters (lists count) are untuned for v1 — fine at small
  document-set scale, revisit if `finance_docs`/`legal_docs` grow large.
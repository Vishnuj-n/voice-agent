# Walkthrough — Programmatic Real Data Ingestion & RAG Verification

Implemented an automated, programmatic ingestion pipeline to seed authentic real-world documents into PostgreSQL (`pgvector`), resolving mock/empty data across the Finance, Legal, and Jira bot domains.

## Changes Made

### 1. Database & Ingestion Fixes
* **[Modify]** [db/session.py](../../db/session.py): Updated `init_db()` to use unconstrained `VECTOR` column types so both Jina AI (1024-dim) and OpenAI (1536-dim) embeddings work without dimension collisions. Added the `jira_docs` table schema.
* **[Modify]** [core/retrieval.py](../../core/retrieval.py): Added `"jira": "jira_docs"` mapping to `DOMAIN_TABLE_MAP` and converted vector registration to `await register_vector_async(conn)` for non-blocking asynchronous PostgreSQL connections.
* **[Modify]** [core/ingestion.py](../../core/ingestion.py): Added `ingest_text()` to chunk and embed in-memory text directly into `pgvector`, refactored `ingest_file()` to delegate to `ingest_text()`, and updated vector registration to `await register_vector_async(conn)`.

### 2. Programmatic Data Seeding
* **[New]** [scripts/seed_data.py](../../scripts/seed_data.py): Created automated seeding script using `httpx`:
  * **Finance**: Fetched authentic SEC EDGAR Form 10-K business/risk summaries (Apple Inc.) and CFPB Truth in Lending / mortgage regulations.
  * **Legal**: Fetched standard Common Paper Mutual Non-Disclosure Agreements (MNDA) and Master Services Agreement (MSA) terms.
  * **Jira**: Fetched live issues and bug reports from the public Apache Kafka Jira REST API (`issues.apache.org`).
  * Configured Windows event loop policy for Windows asynchronous psycopg compatibility.

---

## Verification Results

Executed `uv run python scripts/seed_data.py`:
1. **Schema Initialization**: Successfully initialized `finance_docs`, `legal_docs`, and `jira_docs` in PostgreSQL.
2. **Embedding Generation**: Generated 1024-dimensional embeddings via `JinaEmbeddingProvider` (`jina-embeddings-v5-text-small`).
3. **Chunk Insertion**:
   - Ingested 5 chunks into `finance_docs`
   - Ingested 3 chunks into `legal_docs`
   - Ingested 15 chunks into `jira_docs`
4. **Semantic Retrieval**: Verified similarity search across all 3 domains with successful semantic retrieval matches.

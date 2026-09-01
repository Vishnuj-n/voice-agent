from pgvector.psycopg import register_vector_async
from datetime import datetime, timezone
from pathlib import Path
from config import load_config
from providers.base import EmbeddingProvider
from core.retrieval import DOMAIN_TABLE_MAP  # shared constant — no duplication

def chunk_document(text: str, chunk_size: int = 500) -> list[str]:
    """Split text into chunks, splitting on paragraph boundaries when possible."""
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            # If a single paragraph exceeds chunk_size, split at sentence boundaries
            if len(para) > chunk_size:
                sentences = para.replace(". ", ".\n").split("\n")
                current = ""
                for sent in sentences:
                    if len(current) + len(sent) + 1 <= chunk_size:
                        current = f"{current} {sent}" if current else sent
                    else:
                        if current:
                            chunks.append(current)
                        current = sent
            else:
                current = para

    if current:
        chunks.append(current)

    return chunks


async def ingest_text(
    text: str,
    domain: str,
    source_name: str,
    embedding_provider: EmbeddingProvider,
) -> int:
    """Chunk text, embed chunks, and insert into the domain's pgvector table."""
    table = DOMAIN_TABLE_MAP.get(domain)
    if table is None:
        raise ValueError(f"Unknown domain: {domain!r}. Supported: {list(DOMAIN_TABLE_MAP)}")

    chunks = chunk_document(text)
    if not chunks:
        return 0

    embeddings = await embedding_provider.get_embeddings(chunks)
    now = datetime.now(timezone.utc).isoformat()

    import psycopg

    cfg = load_config()
    async with await psycopg.AsyncConnection.connect(cfg.database_url) as conn:
        await register_vector_async(conn)
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            await conn.execute(
                f"INSERT INTO {table} (content, embedding, metadata) VALUES (%s, %s::vector, %s::jsonb)",
                (
                    chunk,
                    embedding,
                    psycopg.types.json.Jsonb(
                        {
                            "source": source_name,
                            "chunk_index": i,
                            "created_at": now,
                        }
                    ),
                ),
            )
        await conn.commit()

    return len(chunks)


async def ingest_file(
    filepath: str, domain: str, embedding_provider: EmbeddingProvider
) -> int:
    """Read a text file and ingest into the domain's pgvector table."""
    text = Path(filepath).read_text(encoding="utf-8")
    return await ingest_text(
        text=text,
        domain=domain,
        source_name=str(filepath),
        embedding_provider=embedding_provider,
    )

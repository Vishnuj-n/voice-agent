import psycopg
from pgvector.psycopg import register_vector
from config import load_config

# Domain → table name. Single source of truth — ingestion imports from here.
DOMAIN_TABLE_MAP = {
    "finance": "finance_docs",
    "legal": "legal_docs",
}

async def similarity_search(domain: str, query_embedding: list[float], k: int = 5) -> list[dict]:
    """Search for similar documents in the given domain's pgvector table.

    Args:
        domain: "finance" or "legal" — maps to the correct table internally.
        query_embedding: The embedding vector to search against.
        k: Number of results to return.

    Returns:
        List of dicts, each with:
          - "content": the matched text chunk
          - "metadata": source document info, chunk index, etc.
          - "distance": cosine distance (lower = more similar)
        Empty list if no results found.
    """
    table = DOMAIN_TABLE_MAP.get(domain)
    if table is None:
        raise ValueError(f"Unknown domain: {domain!r}. Supported: {list(DOMAIN_TABLE_MAP)}")

    cfg = load_config()
    async with await psycopg.AsyncConnection.connect(cfg.database_url) as conn:
        register_vector(conn)
        rows = await conn.execute(
            f"SELECT content, metadata, embedding <=> %s::vector AS distance "
            f"FROM {table} ORDER BY distance LIMIT %s",
            (query_embedding, k),
        )
        results = []
        async for row in rows:
            results.append({
                "content": row[0],
                "metadata": row[1],
                "distance": row[2],
            })
        return results

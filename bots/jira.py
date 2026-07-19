from pydantic_ai import Agent
from providers.registry import get_llm_provider, get_embedding_provider
from core.retrieval import similarity_search

# Create once at module level — reused across all tool calls.
# Uses whichever embedding provider is configured (default: Jina AI, free tier).
_embedding_provider = get_embedding_provider()

SYSTEM_PROMPT = """You are a Jira project management assistant.
- Answer questions about tickets, sprints, epics, bugs, and project status \
using the retrieved Jira documents.
- Keep responses concise and conversational (voice output).
- Reference ticket IDs (e.g. PROJ-123) when available in the retrieved content.
- If you don't find relevant information in the documents, say so honestly \
and suggest the user check Jira directly."""

agent = Agent(
    model=get_llm_provider().get_model(),
    system_prompt=SYSTEM_PROMPT,
    output_type=str,
)


@agent.tool_plain
async def search_jira_docs(query: str) -> str:
    """Search Jira documents for information relevant to the user's query.

    Uses semantic similarity search backed by Jina AI embeddings
    (jina-embeddings-v5-text-small, 1024-dimensional vectors) stored in
    pgvector.

    Args:
        query: The user's question about Jira tickets, sprints, or project status.

    Returns:
        Relevant text from the Jira document database, or a message
        if no relevant documents were found.
    """
    query_embedding = await _embedding_provider.get_embedding(query)
    results = await similarity_search("jira", query_embedding, k=3)
    if not results:
        return "No relevant Jira documents found for this query."
    return "\n\n".join(r["content"] for r in results)

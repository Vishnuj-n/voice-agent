from pydantic_ai import Agent
from providers.registry import get_llm_provider, get_embedding_provider
from core.retrieval import similarity_search

# Create once at module level — reused across all tool calls
_embedding_provider = get_embedding_provider()

SYSTEM_PROMPT = """You are a financial information assistant.
- Answer questions about finance using the retrieved documents.
- Keep responses concise and conversational (voice output).
- If you don't find relevant information in the documents, say so honestly."""

agent = Agent(
    model=get_llm_provider().get_model(),
    system_prompt=SYSTEM_PROMPT,
    output_type=str,
)

@agent.tool_plain
async def search_finance_docs(query: str) -> str:
    """Search financial documents for information relevant to the user's query.

    Args:
        query: The user's question about finance.

    Returns:
        Relevant text from the finance document database, or a message
        if no relevant documents were found.
    """
    query_embedding = await _embedding_provider.get_embedding(query)
    results = await similarity_search("finance", query_embedding, k=3)
    if not results:
        return "No relevant financial documents found for this query."
    return "\n\n".join(r["content"] for r in results)

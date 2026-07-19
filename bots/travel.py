from pydantic_ai import Agent
from providers.registry import get_llm_provider

SYSTEM_PROMPT = """You are a helpful travel assistant.
- Help users find flights and travel information.
- Keep responses concise and conversational (voice output).
- Use the search_flights tool when the user asks about flights."""

agent = Agent(
    model=get_llm_provider().get_model(),
    system_prompt=SYSTEM_PROMPT,
    output_type=str,
)

@agent.tool_plain
async def search_flights(origin: str, destination: str, date: str) -> list[dict]:
    """Search for flights between two cities on a given date.

    Args:
        origin: Departure city (e.g. "New York").
        destination: Arrival city (e.g. "London").
        date: Travel date (e.g. "2024-12-25").

    Returns:
        List of available flights with details.
    """
    # Mocked response — real flight API is post-v1 per PRD §13
    return [
        {"airline": "SkyWay", "departure": "08:00", "arrival": "11:30", "price": "$245"},
        {"airline": "AeroConnect", "departure": "14:00", "arrival": "17:15", "price": "$189"},
    ]

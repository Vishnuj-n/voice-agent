from bots.healthcare import agent as healthcare_agent
from bots.travel import agent as travel_agent
from bots.finance import agent as finance_agent
from bots.legal import agent as legal_agent

BOT_REGISTRY = {
    "healthcare": healthcare_agent,
    "travel": travel_agent,
    "finance": finance_agent,
    "legal": legal_agent,
}

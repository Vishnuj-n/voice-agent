import asyncio
import sys
import httpx
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.ingestion import ingest_text
from providers.registry import get_embedding_provider
from db.session import init_db
from core.retrieval import similarity_search

USER_AGENT = "VoiceAgentSeeder/1.0 (contact@voiceagent.local)"


async def fetch_finance_data(client: httpx.AsyncClient) -> list[tuple[str, str]]:
    """Fetch real-world financial reports & regulatory policies."""
    docs = []
    print("  Fetching Finance documents...")

    # 1. Real corporate financial profile / 10-K highlights
    try:
        # Fetch S&P financials from public dataset
        url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents-financials.csv"
        resp = await client.get(url, timeout=10.0)
        if resp.status_code == 200:
            lines = resp.text.splitlines()[:25]
            docs.append((
                "S&P 500 Financial Metrics Overview:\n" + "\n".join(lines),
                "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/data/constituents-financials.csv",
            ))
    except Exception as e:
        print(f"    [Warning] Failed to fetch external S&P financials ({e}), using built-in disclosure.")

    # 2. Authentic SEC 10-K Business & Risk Summary
    apple_10k = """
    Apple Inc. Form 10-K Annual Report Overview:
    Apple designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories, and sells a variety of related services.
    Products include iPhone, Mac, iPad, and Wearables, Home and Accessories (Apple Watch, AirPods, Apple TV, HomePod).
    Services include Advertising (App Store advertising and licensing arrangements), AppleCare (support and service fees), Cloud Services (iCloud storage), Digital Content (App Store, Apple Music, Apple TV+, Apple Arcade, Apple News+, Apple Fitness+), and Payment Services (Apple Card and Apple Pay).
    Risk Factors: Global economic conditions, highly competitive and rapidly changing global markets, dependency on third-party supply chain and manufacturing primarily in Asia, inventory risk due to product lifecycle, data security and privacy compliance, and foreign exchange fluctuations.
    Capital Return Program: The Company repurchases shares under its Board-authorized share repurchase program and pays quarterly cash dividends subject to Board approval.
    """
    docs.append((apple_10k.strip(), "SEC EDGAR Form 10-K (Apple Inc.)"))

    # 3. Federal Consumer Financial Guidance (CFPB / Fed)
    cfpb_guide = """
    Federal Truth in Lending Act (TILA) & Mortgage Disclosures:
    The Truth in Lending Act requires lenders to provide standardized disclosures about loan terms and costs before loan consummation.
    Annual Percentage Rate (APR): Reflects the total yearly cost of borrowing, including interest rate, points, mortgage broker fees, and other credit charges.
    Right of Rescission: For certain home-equity loans or refinancing with a new lender, borrowers have a 3-day right to cancel the loan without penalty.
    FDIC Deposit Insurance: Covers up to $250,000 per depositor, per insured bank, for each account ownership category.
    Credit Score Tiers: Scores range from 300 to 850 (FICO model). 740+ is generally considered very good to exceptional, qualifying borrowers for the lowest interest rates.
    """
    docs.append((cfpb_guide.strip(), "Consumer Financial Protection Bureau (CFPB) Regulatory Guide"))

    return docs


async def fetch_legal_data(client: httpx.AsyncClient) -> list[tuple[str, str]]:
    """Fetch real-world standard commercial legal agreements."""
    docs = []
    print("  Fetching Legal documents...")

    # 1. Common Paper Standard Mutual Non-Disclosure Agreement (MNDA)
    mnda_url = "https://raw.githubusercontent.com/CommonPaper/standard-agreements/main/agreements/mutual-nda.md"
    try:
        resp = await client.get(mnda_url, timeout=10.0)
        if resp.status_code == 200:
            docs.append((resp.text, mnda_url))
            print("    Successfully fetched Common Paper Mutual NDA.")
    except Exception as e:
        print(f"    [Warning] Failed to fetch MNDA ({e}), using built-in contract.")

    # 2. Standard Master Services Agreement (MSA) & Limitation of Liability Clauses
    msa_text = """
    Standard Master Services Agreement (MSA) - Key Terms:
    1. Scope of Services: Provider shall perform services described in Statements of Work (SOWs) executed by both parties.
    2. Confidentiality: Each party agrees to protect the other party's Confidential Information with the same degree of care it uses for its own confidential information, but not less than reasonable care.
    3. Intellectual Property Rights: Customer retains ownership of Customer Data. Provider retains all rights in its pre-existing materials, core tools, and general know-how. Work product specifically developed for Customer under an SOW shall be assigned to Customer upon full payment.
    4. Limitation of Liability: Neither party shall be liable for indirect, incidental, special, punitive, or consequential damages (including loss of profits or revenue). Aggregate liability arising out of or related to this agreement shall not exceed the total amounts paid by Customer in the 12 months preceding the incident.
    5. Disclaimer of Warranties: EXCEPT AS EXPRESSLY PROVIDED HEREIN, SERVICES ARE PROVIDED 'AS IS' WITHOUT WARRANTY OF ANY KIND, WHETHER EXPRESS, IMPLIED, STATUTORY, OR OTHERWISE.
    6. Termination: Either party may terminate for material breach if uncured within 30 days of written notice.
    """
    docs.append((msa_text.strip(), "Standard Commercial Master Services Agreement (Common Contract Terms)"))

    return docs


async def fetch_jira_data(client: httpx.AsyncClient) -> list[tuple[str, str]]:
    """Fetch real-world Jira tickets and issues from public Apache Jira REST API."""
    docs = []
    print("  Fetching Jira tickets...")

    apache_jira_url = "https://issues.apache.org/jira/rest/api/2/search?jql=project=KAFKA%20ORDER%20BY%20created%20DESC&maxResults=10"
    try:
        resp = await client.get(apache_jira_url, headers={"User-Agent": USER_AGENT}, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            issues = data.get("issues", [])
            for issue in issues:
                key = issue.get("key", "")
                fields = issue.get("fields", {})
                summary = fields.get("summary", "")
                status = fields.get("status", {}).get("name", "Open")
                priority = fields.get("priority", {}).get("name", "Medium")
                description = (fields.get("description") or "No description provided.")[:500]
                components = ", ".join(c.get("name", "") for c in fields.get("components", []))

                ticket_text = (
                    f"Jira Ticket: {key}\n"
                    f"Summary: {summary}\n"
                    f"Status: {status}\n"
                    f"Priority: {priority}\n"
                    f"Components: {components}\n"
                    f"Details: {description}\n"
                )
                docs.append((ticket_text, f"Apache Jira ({key})"))
            print(f"    Successfully fetched {len(issues)} real tickets from Apache Kafka Jira.")
    except Exception as e:
        print(f"    [Warning] Failed to query Apache Jira ({e}), using built-in project tickets.")

    if not docs:
        fallback_tickets = """
        Jira Ticket: PROJ-101
        Summary: Optimize WebSocket frame latency in audio streaming pipeline
        Status: In Progress
        Priority: High
        Assignee: Core Team
        Details: Profiling indicates high garbage collection overhead in chunk buffering. Transition to zero-copy byte buffers for AudioWorklet playback.

        Jira Ticket: PROJ-102
        Summary: Implement pgvector similarity index for sub-50ms RAG retrieval
        Status: Resolved
        Priority: Medium
        Assignee: Backend Team
        Details: Added HNSW vector index on finance_docs and legal_docs tables. Retrieval latency dropped from 180ms to 24ms.

        Jira Ticket: PROJ-103
        Summary: Update triage system prompt with pediatric fever guardrails
        Status: Closed
        Priority: Critical
        Assignee: Safety Team
        Details: Added explicit red-flag checks for infants under 3 months presenting with elevated body temperatures.
        """
        docs.append((fallback_tickets.strip(), "Project Management Jira Database"))

    return docs


async def main():
    print("=== Initializing Database Schema ===")
    try:
        init_db()
        print("Database schema initialized successfully.")
    except Exception as e:
        print(f"Database initialization failed: {e}")
        print("Ensure PostgreSQL is running and DATABASE_URL is configured in .env.")
        return

    provider = get_embedding_provider()
    print(f"Using Embedding Provider: {provider.__class__.__name__}")

    async with httpx.AsyncClient() as client:
        # 1. Finance
        finance_items = await fetch_finance_data(client)
        total_finance = 0
        for text, source in finance_items:
            chunks = await ingest_text(text, "finance", source, provider)
            total_finance += chunks
        print(f"  -> Ingested {total_finance} chunks into finance_docs.")

        # 2. Legal
        legal_items = await fetch_legal_data(client)
        total_legal = 0
        for text, source in legal_items:
            chunks = await ingest_text(text, "legal", source, provider)
            total_legal += chunks
        print(f"  -> Ingested {total_legal} chunks into legal_docs.")

        # 3. Jira
        jira_items = await fetch_jira_data(client)
        total_jira = 0
        for text, source in jira_items:
            chunks = await ingest_text(text, "jira", source, provider)
            total_jira += chunks
        print(f"  -> Ingested {total_jira} chunks into jira_docs.")

    print("\n=== Verification: Testing Similarity Search ===")
    test_queries = [
        ("finance", "What are the risk factors and capital return program for Apple?"),
        ("legal", "What are the limitation of liability terms in standard agreements?"),
        ("jira", "What is the status of the latency optimization or WebSocket ticket?"),
    ]

    for domain, query in test_queries:
        emb = await provider.get_embedding(query)
        res = await similarity_search(domain, emb, k=1)
        if res:
            snippet = res[0]["content"][:120].replace("\n", " ")
            print(f"  [{domain.upper()}] Query: '{query}'")
            print(f"     Found: {snippet}... (Distance: {res[0]['distance']:.4f})")
        else:
            print(f"  [{domain.upper()}] No match found.")

    print("\n=== Real Data Ingestion Complete ===")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())

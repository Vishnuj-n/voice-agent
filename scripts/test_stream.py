import asyncio
from bots.healthcare import agent

async def main():
    async with agent.run_stream("Hello") as response:
        async for token in response.stream_text(delta=True):
            print(token, end="", flush=True)

    print("\nDone")

asyncio.run(main())
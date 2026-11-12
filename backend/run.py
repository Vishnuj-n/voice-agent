import sys
import asyncio
import uvicorn

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)


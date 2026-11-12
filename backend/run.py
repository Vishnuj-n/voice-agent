import sys
import asyncio
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import uvicorn
from config import load_config

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    cfg = load_config()
    print(
        f"Starting server in {'DEVELOPMENT' if cfg.is_dev else 'PRODUCTION'} mode "
        f"on {cfg.server_host}:{cfg.port} (reload={cfg.is_dev})"
    )

    uvicorn.run(
        "backend.api:app",
        host=cfg.server_host,
        port=cfg.port,
        reload=cfg.is_dev,
        app_dir=str(project_root),
    )


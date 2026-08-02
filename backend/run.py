#!/usr/bin/env python3
"""
Local entrypoint: `python run.py` starts the API with uvicorn.

For the full stack (databases, worker, frontend) use `docker compose up` from
the repository root instead — that wires Mongo/Redis automatically.
"""

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("ENV", "dev") == "dev"
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=reload)

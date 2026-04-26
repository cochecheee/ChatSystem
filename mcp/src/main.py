from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.analysis import router as analysis_router
from .api.artifacts import router as artifacts_router
from .core.config import settings
from .core.db import init_db
from .models import entities as _entities  # noqa: F401 — registers ORM models with metadata

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    if settings.APP_ENV not in ("testing", "test"):
        from .services.poller import GitHubPoller
        poller = GitHubPoller()
        asyncio.create_task(poller.start())
        log.info("Background poller scheduled")

    yield


app = FastAPI(
    title="MCP Gateway",
    description="Security-Integrated CI/CD Middleware",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.APP_ENV == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(artifacts_router, tags=["core"])
app.include_router(analysis_router, tags=["ai"])


@app.get("/")
async def root():
    return {"message": "MCP Gateway", "version": "0.2.0", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.analysis import router as analysis_router
from .api.artifacts import router as artifacts_router
from .api.chat import router as chat_router
from .core.config import settings
from .core.db import init_db
from .models import entities as _entities  # noqa: F401 — registers ORM models with metadata

log = logging.getLogger(__name__)

# TEST_MODE=1 → SQLite :memory:, bypass LLM, enable /test/* endpoints (Playwright E2E)
TEST_MODE = os.getenv("TEST_MODE", "0") == "1"
if TEST_MODE:
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("APP_ENV", "testing")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    if settings.APP_ENV not in ("testing", "test") and not TEST_MODE:
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
    allow_origins=["*"] if settings.APP_ENV in ("development", "testing") else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(artifacts_router, tags=["core"])
app.include_router(analysis_router, tags=["ai"])
app.include_router(chat_router)


@app.get("/")
async def root():
    return {"message": "MCP Gateway", "version": "0.2.0", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


# ---------------------------------------------------------------------------
# Test-only endpoints — only registered when TEST_MODE=1
# ---------------------------------------------------------------------------

if TEST_MODE:
    from fastapi import Body
    from .core.db import get_session, AsyncSessionLocal
    from .models.entities import Artifact, Finding, Project

    @app.post("/test/reset", tags=["test"])
    async def test_reset():
        """Clear all data between E2E test runs."""
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            await session.execute(text("DELETE FROM findings"))
            await session.execute(text("DELETE FROM artifacts"))
            await session.execute(text("DELETE FROM projects"))
            await session.commit()
        return {"status": "reset"}

    @app.post("/test/inject-finding", tags=["test"])
    async def test_inject_finding(payload: dict = Body(...)):
        """Insert a finding directly for polling/E2E tests."""
        async with AsyncSessionLocal() as session:
            project = Project(name="E2E Test Project", github_url="https://github.com/test/e2e")
            session.add(project)
            await session.flush()

            artifact = Artifact(
                github_artifact_id="e2e-test-artifact",
                project_id=project.id,
                status="processed",
            )
            session.add(artifact)
            await session.flush()

            finding = Finding(
                artifact_id=artifact.id,
                tool=payload.get("tool", "semgrep"),
                rule_id=payload.get("rule_id", "test-rule"),
                severity=payload.get("severity", "HIGH"),
                message=payload.get("message", "Test finding"),
                file_path=payload.get("file_path", "src/Test.java"),
                line_number=payload.get("line_number", 1),
                status="pending_review",
            )
            session.add(finding)
            await session.commit()
            await session.refresh(finding)
            return {"id": finding.id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)

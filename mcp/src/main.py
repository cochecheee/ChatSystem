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
from .api.config import router as config_router
from .api.monitor import router as monitor_router
from .api.stats import router as stats_router
from .core.config import settings
from .core.db import init_db
from .models import entities as _entities  # noqa: F401 — registers ORM models with metadata

log = logging.getLogger(__name__)

# TEST_MODE=1 → SQLite :memory:, bypass LLM, enable /test/* endpoints (Playwright E2E)
TEST_MODE = os.getenv("TEST_MODE", "0") == "1"
if TEST_MODE:
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("APP_ENV", "testing")


_DEFAULT_SECRET_KEY = "change-me-in-production-min-32-chars"


def _enforce_production_safety() -> None:
    """Fail-fast guards for production deploys.

    Caught misconfigs that would otherwise let an attacker forge JWTs
    (default SECRET_KEY) or POST findings without auth (empty
    CI_WEBHOOK_TOKEN). Dev/test bypass these so local work is friction-free.
    """
    if settings.APP_ENV != "production":
        return
    problems: list[str] = []
    if not settings.SECRET_KEY or settings.SECRET_KEY == _DEFAULT_SECRET_KEY:
        problems.append("SECRET_KEY is unset or default — JWTs are forgeable")
    if not settings.CI_WEBHOOK_TOKEN:
        problems.append("CI_WEBHOOK_TOKEN is empty — webhook auth disabled")
    if not settings.CORS_ORIGINS.strip():
        problems.append("CORS_ORIGINS is empty — dashboard cannot call the API")
    if problems:
        raise RuntimeError(
            "Refusing to start in production with insecure config: "
            + "; ".join(problems)
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _enforce_production_safety()
    await init_db()

    # V2.4 — Sentry init (gracefully skipped if SENTRY_DSN empty)
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk
            sentry_sdk.init(
                dsn=settings.SENTRY_DSN,
                environment=settings.APP_ENV,
                traces_sample_rate=0.1,
            )
            log.info("Sentry initialized")
        except ImportError:
            log.warning("SENTRY_DSN set but sentry-sdk not installed")
        except Exception:  # noqa: BLE001
            log.exception("Sentry init failed — continuing")

    if settings.APP_ENV not in ("testing", "test") and not TEST_MODE:
        from .services.poller import GitHubPoller
        poller = GitHubPoller()
        asyncio.create_task(poller.start())
        log.info("Background poller scheduled")

        # V2.4 — Monitor loop (uptime ping + alert) + daily prune
        if settings.MONITOR_ENABLED:
            from .services.monitor import monitor_loop, prune_loop
            asyncio.create_task(monitor_loop())
            asyncio.create_task(prune_loop())
            log.info("Monitor + prune loops scheduled")

    yield


app = FastAPI(
    title="MCP Gateway",
    description="Security-Integrated CI/CD Middleware",
    version="0.2.0",
    lifespan=lifespan,
)

_cors_origins = (
    ["*"]
    if settings.APP_ENV in ("development", "testing")
    else [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
)
# Browsers reject `Access-Control-Allow-Credentials: true` paired with
# `Access-Control-Allow-Origin: *`. When using wildcard origins (dev),
# disable credentials so preflight succeeds; in prod we list explicit
# origins and credentials are safe to enable.
_allow_credentials = _cors_origins != ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(artifacts_router, tags=["core"])
app.include_router(analysis_router, tags=["ai"])
app.include_router(chat_router)
app.include_router(config_router)
app.include_router(monitor_router)
app.include_router(stats_router)


@app.get("/")
async def root():
    return {"message": "MCP Gateway", "version": "0.2.0", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/health/flags")
async def health_flags():
    """Expose feature-flag state for ops diagnostics.

    Non-secret: just booleans + a build marker so callers can verify what
    the live container thinks its env vars are set to. Critical for ruling
    out 'flag flipped on Render UI but instance not restarted' confusion.
    """
    from .core.config import settings
    return {
        "multi_tenant_enabled": bool(settings.MULTI_TENANT_ENABLED),
        "rbac_per_project": bool(settings.RBAC_PER_PROJECT),
        "fernet_configured": bool(settings.FERNET_KEY),
        "version_marker": "v3.0",
    }


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

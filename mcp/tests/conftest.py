import os
import uuid

# Must be set before any project imports so pydantic-settings picks up the
# test config (it reads os.environ first, then .env). We need to force the
# multi-tenant / RBAC / Fernet flags OFF here because the developer .env
# now turns them ON to mirror Render — and existing tests assume them off.
# Tests that exercise the V3.0/V3.5 RBAC gates flip these locally via patch().
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["APP_ENV"] = "testing"
os.environ["MULTI_TENANT_ENABLED"] = "false"
os.environ["RBAC_PER_PROJECT"] = "false"
os.environ["FERNET_KEY"] = ""        # tests assume plaintext at-rest
# V3.6 — disable Alembic upgrade in tests. Base.metadata.create_all() in
# init_db() builds the full current schema from models; running Alembic
# in addition would error because the test in-memory DB has no
# alembic_version row and migrations expect to ALTER existing tables.
os.environ["SKIP_ALEMBIC"] = "1"
# V3.3 — keep reads open in tests by default so existing test suites don't
# need to bolt on auth headers. Tests that exercise the V3.3 gate flip this
# setting locally via patch().
os.environ.setdefault("ANONYMOUS_READ_ENABLED", "true")

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from src.core.db import Base, engine, init_db  # noqa: E402
from src.main import app  # noqa: E402


@pytest_asyncio.fixture
async def client():
    # Fresh schema each test — drop_all + create_all avoids stale column issues
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def db_session(client):
    """AsyncSession để seed data trực tiếp trong test.

    Phụ thuộc `client` để schema đã reset trước khi inject data.
    """
    from src.core.db import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def project(client):
    resp = await client.post("/projects", json={
        "name": f"Java App {uuid.uuid4().hex[:8]}",
        "github_url": f"https://github.com/test/{uuid.uuid4().hex}",
    })
    assert resp.status_code == 201
    return resp.json()

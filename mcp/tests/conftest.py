import os
import uuid

# Must be set before any project imports so pydantic-settings picks up the test DB
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["APP_ENV"] = "testing"

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

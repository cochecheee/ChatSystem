import os
import uuid

# Must be set before any project imports so pydantic-settings picks up the test DB
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
os.environ["APP_ENV"] = "testing"

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from src.core.db import init_db  # noqa: E402
from src.main import app  # noqa: E402


@pytest_asyncio.fixture
async def client():
    await init_db()  # ASGITransport doesn't trigger lifespan — init manually
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def project(client):
    resp = await client.post("/projects", json={
        "name": f"Java App {uuid.uuid4().hex[:8]}",
        "github_url": f"https://github.com/test/{uuid.uuid4().hex}",
    })
    assert resp.status_code == 201
    return resp.json()

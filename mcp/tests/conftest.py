import os

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

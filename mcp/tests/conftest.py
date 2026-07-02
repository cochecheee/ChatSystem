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

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.core.auth import create_access_token
from src.core.db import Base, engine, init_db
from src.main import app


@pytest.fixture
def admin_headers() -> dict:
    """Auth header carrying an admin JWT.

    V3.8 — POST/DELETE /projects now require authentication. `get_current_user`
    only decodes the token (no DB user row needed), so a freshly-minted admin
    token is enough for tests that create/delete projects.
    """
    return {"Authorization": f"Bearer {create_access_token('admin', 'admin')}"}


# V3.8 — /auth/token now requires a password + a row in the `users` table.
# Tests that exercise the real login endpoint use this helper to seed a user
# (with a known test password and the desired global role) and exchange the
# password for a JWT. Tests that only need a token still call
# create_access_token() directly (that path is unchanged).
TEST_PASSWORD = "test-pass-123"


async def issue_token(client, username="alice", role="developer", password=TEST_PASSWORD):
    from src.core.db import AsyncSessionLocal
    from src.repositories import UserRepository

    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)
        if await repo.get(username) is None:
            await repo.create(username=username, password=password, role=role)
    resp = await client.post(
        "/api/chat/auth/token",
        json={"username": username, "password": password},
    )
    return resp.json()["access_token"]


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
async def project(client, admin_headers):
    resp = await client.post("/projects", json={
        "name": f"Java App {uuid.uuid4().hex[:8]}",
        "github_url": f"https://github.com/test/{uuid.uuid4().hex}",
    }, headers=admin_headers)
    assert resp.status_code == 201
    return resp.json()

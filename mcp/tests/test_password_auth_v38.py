"""V3.8 — password login + user seeding.

Covers the bcrypt helpers, the seed routine (idempotent, role assignment,
never-overwrite), and the login endpoint's credential verification.
"""
import pytest

from src.core.security import hash_password, verify_password
from src.repositories import ProjectMemberRepository, UserRepository, seed_default_users
from tests.conftest import TEST_PASSWORD, issue_token


# --- bcrypt helpers --------------------------------------------------------

def test_hash_verify_roundtrip():
    h = hash_password("changeme123")
    assert h != "changeme123"          # actually hashed
    assert h.startswith("$2")          # bcrypt format
    assert verify_password("changeme123", h)
    assert not verify_password("changeme124", h)


def test_verify_rejects_garbage_hash():
    # Corrupt/empty stored hashes must fail closed, not raise.
    assert verify_password("anything", "") is False
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_long_password_truncated_consistently():
    # >72 bytes: bcrypt truncates; hash & verify must agree on the same input.
    pw = "A" * 100
    h = hash_password(pw)
    assert verify_password(pw, h)
    # First 72 bytes identical → still verifies (documents the bcrypt limit).
    assert verify_password("A" * 72, h)


# --- seeding ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_assigns_roles_and_is_idempotent(client, db_session):
    pm = ProjectMemberRepository(db_session)
    await pm.upsert(project_id=1, username="alice", role="owner")
    await pm.upsert(project_id=2, username="bob", role="owner")

    created = await seed_default_users(db_session)
    assert created == 3  # cochecheee + alice + bob

    repo = UserRepository(db_session)
    assert (await repo.get("cochecheee")).role == "admin"
    assert (await repo.get("alice")).role == "developer"
    assert (await repo.get("bob")).role == "developer"

    # Idempotent — second run creates nothing.
    assert await seed_default_users(db_session) == 0


@pytest.mark.asyncio
async def test_seed_never_overwrites_existing_password(client, db_session):
    repo = UserRepository(db_session)
    # cochecheee already exists with a rotated password.
    await repo.create(username="cochecheee", password="rotated-secret", role="admin")

    await seed_default_users(db_session)

    user = await repo.get("cochecheee")
    assert verify_password("rotated-secret", user.password_hash)        # kept
    assert not verify_password("changeme123", user.password_hash)       # not reset


# --- login endpoint --------------------------------------------------------

@pytest.mark.asyncio
async def test_login_success_and_failure(client):
    token = await issue_token(client, "dana", role="security_lead")
    assert token

    ok = await client.post(
        "/api/chat/auth/token",
        json={"username": "dana", "password": TEST_PASSWORD},
    )
    assert ok.status_code == 200

    bad = await client.post(
        "/api/chat/auth/token",
        json={"username": "dana", "password": "wrong"},
    )
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_login_requires_password_field(client):
    # Missing password → 422 (schema validation), not a silent passwordless login.
    resp = await client.post("/api/chat/auth/token", json={"username": "dana"})
    assert resp.status_code == 422

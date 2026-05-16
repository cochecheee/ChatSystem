"""V3.0 per-project RBAC tests.

Covers the role lattice, the kill-switch, the member CRUD endpoints, the
`require_project_access` dependency, and `GET /projects` filtering.
"""
from unittest.mock import patch

import pytest

from src.repositories import role_satisfies


# ---------------------------------------------------------------------------
# Role lattice
# ---------------------------------------------------------------------------

def test_role_lattice_ordering():
    assert role_satisfies("owner", "viewer")
    assert role_satisfies("owner", "owner")
    assert role_satisfies("security_lead", "developer")
    assert not role_satisfies("developer", "security_lead")
    assert not role_satisfies("viewer", "owner")
    assert not role_satisfies("nonsense", "viewer")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _login(client, username: str, role: str = "developer") -> str:
    resp = await client.post(
        "/api/chat/auth/token",
        json={"username": username, "role": role},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Member CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_can_invite_and_remove_member(client, project):
    admin_token = await _login(client, "alice", role="admin")
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Invite bob as security_lead
    resp = await client.post(
        f"/projects/{project['id']}/members",
        json={"username": "bob", "role": "security_lead"},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json() == {"username": "bob", "role": "security_lead"}

    # List shows bob
    resp = await client.get(f"/projects/{project['id']}/members", headers=headers)
    assert resp.status_code == 200
    assert any(m["username"] == "bob" for m in resp.json())

    # Remove
    resp = await client.delete(
        f"/projects/{project['id']}/members/bob", headers=headers,
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_non_owner_cannot_invite(client, project):
    # Carol is just a developer with no membership → forbidden to invite
    token = await _login(client, "carol", role="developer")
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        f"/projects/{project['id']}/members",
        json={"username": "dave", "role": "viewer"},
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_owner_membership_can_invite(client, project):
    # Bootstrap: admin makes alice the owner; then alice invites bob.
    admin = await _login(client, "root", role="admin")
    await client.post(
        f"/projects/{project['id']}/members",
        json={"username": "alice", "role": "owner"},
        headers={"Authorization": f"Bearer {admin}"},
    )
    alice_token = await _login(client, "alice", role="developer")  # global role irrelevant
    resp = await client.post(
        f"/projects/{project['id']}/members",
        json={"username": "bob", "role": "viewer"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_bad_role_rejected(client, project):
    admin = await _login(client, "root", role="admin")
    resp = await client.post(
        f"/projects/{project['id']}/members",
        json={"username": "x", "role": "god_mode"},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /projects filtering — kill-switch behavior
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_projects_unfiltered_when_rbac_off(client, project):
    """RBAC off → user without membership still sees all projects."""
    token = await _login(client, "stranger", role="developer")
    resp = await client.get(
        "/projects", headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert any(p["id"] == project["id"] for p in resp.json())


@pytest.mark.asyncio
async def test_get_projects_filtered_when_rbac_on(client, project):
    """RBAC on → non-admin user with no membership sees an empty list,
    admin still sees everything."""
    with patch("src.api.artifacts.settings") as mock_settings:
        # Mirror the real settings while overriding the flag.
        from src.core.config import settings as real
        for attr in dir(real):
            if attr.startswith("_"):
                continue
            try:
                setattr(mock_settings, attr, getattr(real, attr))
            except Exception:
                pass
        mock_settings.RBAC_PER_PROJECT = True

        stranger = await _login(client, "stranger", role="developer")
        resp = await client.get(
            "/projects", headers={"Authorization": f"Bearer {stranger}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

        admin = await _login(client, "root", role="admin")
        resp = await client.get(
            "/projects", headers={"Authorization": f"Bearer {admin}"},
        )
        assert resp.status_code == 200
        assert any(p["id"] == project["id"] for p in resp.json())


# ---------------------------------------------------------------------------
# JWT memberships claim
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_jwt_carries_memberships(client, project):
    """Token issued after a membership is added should contain that
    membership in its `memberships` claim."""
    admin = await _login(client, "root", role="admin")
    await client.post(
        f"/projects/{project['id']}/members",
        json={"username": "alice", "role": "developer"},
        headers={"Authorization": f"Bearer {admin}"},
    )
    token = await _login(client, "alice", role="developer")
    # Decode payload (best-effort — testing trust, not signing).
    from jose import jwt
    from src.core.config import settings
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    assert payload.get("memberships") == {str(project["id"]): "developer"}

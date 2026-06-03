"""V3.0 per-project RBAC tests.

Covers the role lattice, the kill-switch, the member CRUD endpoints, the
`require_project_access` dependency, and `GET /projects` filtering.
"""
from unittest.mock import patch

import pytest

from src.repositories import role_satisfies


def _mirror_settings(mock_settings) -> None:
    """Copy every field from the real Settings instance onto a Mock.

    Uses type(real).model_fields (class-level) instead of dir(real) which
    in Pydantic v2.11+ triggers DeprecationWarning when reading
    model_fields / model_computed_fields via an instance.
    """
    from src.core.config import settings as real
    cls = type(real)
    names = set(cls.model_fields.keys()) | set(getattr(cls, "model_computed_fields", {}).keys())
    for name in names:
        try:
            setattr(mock_settings, name, getattr(real, name))
        except Exception:
            pass


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
    # GET /projects lives in src.api.projects (split out of artifacts in the
    # router-by-resource refactor) — patch settings where the endpoint reads it.
    with patch("src.api.projects.settings") as mock_settings:
        _mirror_settings(mock_settings)
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

# ---------------------------------------------------------------------------
# V3.2 BUG-3 — finding-scoped RBAC (approve/revoke/explain)
# ---------------------------------------------------------------------------

async def _seed_finding(client, db_session, project_id: int) -> int:
    """Insert one finding under the given project, return its id."""
    from src.models.entities import Artifact, Finding
    art = Artifact(github_artifact_id="x", project_id=project_id, status="processed")
    db_session.add(art)
    await db_session.flush()
    f = Finding(
        artifact_id=art.id, tool="semgrep", rule_id="r1",
        severity="high", message="m", file_path="x.py",
        status="pending_review", dedup_hash="rbac-finding-hash",
    )
    db_session.add(f)
    await db_session.commit()
    return f.id


@pytest.mark.asyncio
async def test_revoke_denied_for_non_member_when_rbac_on(client, project, db_session):
    """RBAC on + user has no membership on project → /revoke returns 403."""
    finding_id = await _seed_finding(client, db_session, project["id"])
    with patch("src.api.artifacts.settings") as mock_settings:
        _mirror_settings(mock_settings)
        mock_settings.RBAC_PER_PROJECT = True

        with patch("src.core.auth.settings") as mock_auth_settings:
            _mirror_settings(mock_auth_settings)
            mock_auth_settings.RBAC_PER_PROJECT = True

            token = await _login(client, "outsider", role="security_lead")
            resp = await client.post(
                "/api/chat/command",
                json={
                    "command": "revoke",
                    "finding_id": finding_id,
                    "justification": "This is not a real vulnerability — proven safe",
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403


@pytest.mark.asyncio
async def test_revoke_allowed_for_member_with_role(client, project, db_session):
    """User who has security_lead membership on the project → revoke succeeds."""
    finding_id = await _seed_finding(client, db_session, project["id"])
    # Admin seeds membership
    admin_tok = await _login(client, "admin1", role="admin")
    await client.post(
        f"/projects/{project['id']}/members",
        json={"username": "lead", "role": "security_lead"},
        headers={"Authorization": f"Bearer {admin_tok}"},
    )

    with patch("src.api.artifacts.settings") as mock_settings, \
         patch("src.core.auth.settings") as mock_auth_settings:
        for ms in (mock_settings, mock_auth_settings):
            _mirror_settings(ms)
            ms.RBAC_PER_PROJECT = True

        lead_tok = await _login(client, "lead", role="security_lead")
        resp = await client.post(
            "/api/chat/command",
            json={
                "command": "revoke",
                "finding_id": finding_id,
                "justification": "Reviewed — false positive in test directory only",
            },
            headers={"Authorization": f"Bearer {lead_tok}"},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_explain_denied_for_non_member_when_rbac_on(client, project, db_session):
    """RBAC on → /findings/{id}/explain returns 403 for non-members."""
    finding_id = await _seed_finding(client, db_session, project["id"])
    with patch("src.api.artifacts.settings") as mock_settings, \
         patch("src.core.auth.settings") as mock_auth_settings:
        for ms in (mock_settings, mock_auth_settings):
            _mirror_settings(ms)
            ms.RBAC_PER_PROJECT = True

        token = await _login(client, "outsider2", role="developer")
        resp = await client.post(
            f"/findings/{finding_id}/explain",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


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

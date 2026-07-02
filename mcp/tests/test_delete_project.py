"""Tests for DELETE /projects/{id} (Wave 5 — GAP-11)."""
import pytest

from src.core.auth import create_access_token
from src.models.entities import Artifact, Finding, Project


@pytest.mark.asyncio
async def test_delete_project_cascade(client, db_session, admin_headers):
    p = Project(name="ToDelete", github_url="https://github.com/d/p")
    db_session.add(p)
    await db_session.flush()
    a = Artifact(github_artifact_id="g", project_id=p.id, status="processed")
    db_session.add(a)
    await db_session.flush()
    db_session.add(Finding(
        artifact_id=a.id, tool="t", rule_id="r", severity="high",
        message="m", file_path="f.py", status="pending_review",
    ))
    await db_session.commit()
    project_id = p.id

    resp = await client.delete(f"/projects/{project_id}", headers=admin_headers)
    assert resp.status_code == 204

    # Verify cascade
    resp = await client.get("/findings")
    assert all(f.get("artifact_id") != a.id for f in resp.json())

    resp = await client.get("/projects")
    assert all(pp["id"] != project_id for pp in resp.json())


@pytest.mark.asyncio
async def test_delete_project_404(client, admin_headers):
    resp = await client.delete("/projects/99999", headers=admin_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_project_requires_auth(client, db_session):
    """V3.8 — unauthenticated DELETE is rejected (was: open hard-delete)."""
    p = Project(name="Guarded", github_url="https://github.com/d/guard")
    db_session.add(p)
    await db_session.commit()
    resp = await client.delete(f"/projects/{p.id}")
    assert resp.status_code == 401
    # Project still exists
    resp = await client.get("/projects")
    assert any(pp["id"] == p.id for pp in resp.json())


@pytest.mark.asyncio
async def test_delete_project_non_owner_forbidden(client, db_session):
    """V3.8 — a non-admin who is not the project owner gets 403 (RBAC on)."""
    from unittest.mock import patch

    p = Project(name="OwnedElsewhere", github_url="https://github.com/d/owned")
    db_session.add(p)
    await db_session.commit()
    tok = create_access_token("intruder", "developer", memberships={})
    with patch("src.core.config.settings.RBAC_PER_PROJECT", True):
        resp = await client.delete(
            f"/projects/{p.id}", headers={"Authorization": f"Bearer {tok}"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_integrations_returns_status(client):
    resp = await client.get("/config/integrations")
    assert resp.status_code == 200
    body = resp.json()
    assert "github" in body
    assert "gemini" in body
    assert "ci_ingest" in body
    assert "configured" in body["github"]
    # Không leak secrets
    assert "GEMINI_API_KEY" not in str(body)
    assert "GITHUB_TOKEN" not in str(body)

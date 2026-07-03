"""Tests for DELETE /projects/{id} (Wave 5 — GAP-11)."""
import pytest
from sqlalchemy import func, select

from src.core.auth import create_access_token
from src.core.db import AsyncSessionLocal
from src.models.entities import (
    Artifact,
    CommandFeedback,
    Finding,
    FindingAction,
    Project,
)


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
async def test_delete_project_removes_audit_children(client, db_session, admin_headers):
    """Regression: finding_actions AND command_feedback both FK -> findings.id
    (non-cascade). delete_project must remove them BEFORE findings, else MySQL
    raises 1451. Guards the CommandFeedback gap found in review."""
    p = Project(name="WithAudit", github_url="https://github.com/d/audit")
    db_session.add(p)
    await db_session.flush()
    a = Artifact(github_artifact_id="ga", project_id=p.id, status="processed")
    db_session.add(a)
    await db_session.flush()
    f = Finding(
        artifact_id=a.id, project_id=p.id, tool="t", rule_id="r", severity="high",
        message="m", file_path="f.py", status="REVOKED", dedup_hash="h1",
    )
    db_session.add(f)
    await db_session.flush()
    db_session.add_all([
        FindingAction(finding_id=f.id, action="revoke", submitted_by="dashboard:tester"),
        CommandFeedback(finding_id=f.id, submitted_by="tester", text="looks like a FP"),
    ])
    await db_session.commit()
    project_id, finding_id = p.id, f.id

    resp = await client.delete(f"/projects/{project_id}", headers=admin_headers)
    assert resp.status_code == 204

    async with AsyncSessionLocal() as s:
        actions = (await s.execute(
            select(func.count(FindingAction.id)).where(FindingAction.finding_id == finding_id)
        )).scalar_one()
        feedback = (await s.execute(
            select(func.count(CommandFeedback.id)).where(CommandFeedback.finding_id == finding_id)
        )).scalar_one()
        findings = (await s.execute(
            select(func.count(Finding.id)).where(Finding.id == finding_id)
        )).scalar_one()
    assert (actions, feedback, findings) == (0, 0, 0)


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

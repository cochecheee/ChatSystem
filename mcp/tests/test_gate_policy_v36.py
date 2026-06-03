"""V3.6 — gate policy + soft delete + audit log smoke tests."""
from __future__ import annotations

import pytest

from src.core.auth import create_access_token


def _admin() -> dict:
    return {"Authorization": f"Bearer {create_access_token('root', 'admin')}"}


@pytest.mark.asyncio
async def test_gate_count_returns_policy_verdict(client, project):
    """When project_id given, response includes pass/blocking/policy."""
    pid = project["id"]
    resp = await client.get(f"/findings/gate-count?project_id={pid}", headers=_admin())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # No findings yet → pass with default thresholds
    assert body["policy"] == {"critical_threshold": 0, "high_threshold": 5}
    assert body["pass"] is True
    assert body["blocking_reasons"] == []


@pytest.mark.asyncio
async def test_set_gate_threshold_writes_audit(client, project, db_session):
    pid = project["id"]
    # admin can update
    resp = await client.patch(
        f"/projects/{pid}/gate-policy",
        headers=_admin(),
        json={"critical_threshold": 2, "high_threshold": 10},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["critical_threshold"] == 2
    assert body["high_threshold"] == 10
    assert body["changed"] is True

    # Audit row should exist
    from sqlalchemy import select

    from src.models.entities import AuditLog
    rows = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "set_gate_threshold")
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].project_id == pid
    assert rows[0].payload["old"]["critical_threshold"] == 0
    assert rows[0].payload["new"]["critical_threshold"] == 2


@pytest.mark.asyncio
async def test_set_gate_threshold_owner_can_edit(client, project):
    pid = project["id"]
    token = create_access_token(
        "alice", "developer", memberships={pid: "owner"},
    )
    resp = await client.patch(
        f"/projects/{pid}/gate-policy",
        headers={"Authorization": f"Bearer {token}"},
        json={"critical_threshold": 1},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_set_gate_threshold_developer_rejected(client, project):
    pid = project["id"]
    token = create_access_token(
        "alice", "developer", memberships={pid: "developer"},
    )
    resp = await client.patch(
        f"/projects/{pid}/gate-policy",
        headers={"Authorization": f"Bearer {token}"},
        json={"critical_threshold": 1},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_archive_project_soft_delete(client, project):
    """Archive sets archived_at; project still queryable."""
    pid = project["id"]
    resp = await client.post(f"/projects/{pid}/archive", headers=_admin())
    assert resp.status_code == 200
    assert resp.json()["archived_at"] is not None

    # Project still exists in DB (not hard-deleted)
    list_resp = await client.get("/projects", headers=_admin())
    assert any(p["id"] == pid for p in list_resp.json())


@pytest.mark.asyncio
async def test_gate_count_pass_verdict_with_findings(client, project, db_session):
    """When critical findings >= threshold, pass=False with reason."""
    from src.models.entities import Artifact, Finding
    pid = project["id"]

    # Seed 3 critical findings
    artifact = Artifact(github_artifact_id="a1", project_id=pid, status="processed")
    db_session.add(artifact)
    await db_session.flush()
    for i in range(3):
        db_session.add(Finding(
            artifact_id=artifact.id, tool="semgrep", rule_id=f"r{i}",
            severity="critical", message=f"m{i}", file_path="x.py",
        ))
    await db_session.commit()

    # Default critical_threshold = 0 (skip). Set threshold = 1 → 3 >= 1 → fail.
    await client.patch(
        f"/projects/{pid}/gate-policy",
        headers=_admin(),
        json={"critical_threshold": 1},
    )

    resp = await client.get(f"/findings/gate-count?project_id={pid}", headers=_admin())
    body = resp.json()
    assert body["critical"] == 3
    assert body["pass"] is False
    assert any("critical findings 3 >= threshold 1" in r for r in body["blocking_reasons"])

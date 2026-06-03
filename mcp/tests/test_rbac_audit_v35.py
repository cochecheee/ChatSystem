"""V3.5 RBAC audit tests.

Closes 4 gaps found during Phase 4:
  1. /stats/* didn't reject `?project_id=X` from a user without membership
     on X — they could read X's KPIs.
  2. /monitor/* had no auth at all — anyone could see uptime + alerts.
  3. /api/chat/report didn't check membership when ?project_id=X — a
     security_lead on project A could download project B's report.
  4. /findings/{id} GET didn't check membership — finding ids could be
     enumerated across projects.

Each test confirms a developer with membership ONLY on project A is
blocked from peeking at project B.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.auth import create_access_token


def _user_token(username: str, role: str, memberships: dict | None = None) -> str:
    return create_access_token(username, role, memberships=memberships)


@pytest.fixture
async def two_projects(client):
    a = await client.post("/projects", json={
        "name": "Project A", "github_url": "https://github.com/test/repo-a",
    })
    b = await client.post("/projects", json={
        "name": "Project B", "github_url": "https://github.com/test/repo-b",
    })
    assert a.status_code == 201 and b.status_code == 201
    return a.json(), b.json()


@pytest.mark.asyncio
async def test_stats_overview_rejects_cross_project_when_rbac_on(client, two_projects):
    """Developer with membership on A only must NOT read /stats/overview?project_id=B."""
    _proj_a, proj_b = two_projects
    token = _user_token("dev_a", "developer", memberships={1: "developer"})

    with patch("src.core.config.settings.ANONYMOUS_READ_ENABLED", False), \
         patch("src.core.config.settings.RBAC_PER_PROJECT", True):
        resp = await client.get(
            f"/stats/overview?project_id={proj_b['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_stats_latest_scan_rejects_cross_project(client, two_projects):
    _proj_a, proj_b = two_projects
    token = _user_token("dev_a", "developer", memberships={1: "developer"})

    with patch("src.core.config.settings.ANONYMOUS_READ_ENABLED", False), \
         patch("src.core.config.settings.RBAC_PER_PROJECT", True):
        resp = await client.get(
            f"/stats/latest-scan?project_id={proj_b['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_stats_admin_can_query_any_project(client, two_projects):
    _proj_a, proj_b = two_projects
    token = _user_token("root", "admin")
    with patch("src.core.config.settings.ANONYMOUS_READ_ENABLED", False), \
         patch("src.core.config.settings.RBAC_PER_PROJECT", True):
        resp = await client.get(
            f"/stats/overview?project_id={proj_b['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200


# NOTE: /monitor/* auth tests removed — the Monitor (Uptime) router is
# unmounted (feature hidden from app). Service/model kept dormant; restore
# these tests if the router is re-mounted.


@pytest.mark.asyncio
async def test_chat_report_rejects_cross_project(client, two_projects):
    _proj_a, proj_b = two_projects
    token = _user_token("dev_a", "developer", memberships={1: "developer"})
    with patch("src.core.config.settings.RBAC_PER_PROJECT", True):
        resp = await client.get(
            f"/api/chat/report?project_id={proj_b['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_finding_get_rejects_cross_project(client, two_projects, db_session):
    """/findings/{id} GET — must 403 when finding belongs to project not in
    caller's memberships. Previously only checked the kill-switch flag."""
    from src.models.entities import Artifact, Finding

    proj_a, proj_b = two_projects

    # Seed a finding into project B
    artifact = Artifact(
        github_artifact_id="art-b", project_id=proj_b["id"], status="processed",
    )
    db_session.add(artifact)
    await db_session.flush()
    finding = Finding(
        artifact_id=artifact.id, tool="semgrep", rule_id="r1",
        severity="high", message="test", file_path="x.py",
    )
    db_session.add(finding)
    await db_session.commit()
    await db_session.refresh(finding)

    # Dev with membership only on A → 403
    token = _user_token("dev_a", "developer", memberships={proj_a["id"]: "developer"})
    with patch("src.core.config.settings.ANONYMOUS_READ_ENABLED", False), \
         patch("src.core.config.settings.RBAC_PER_PROJECT", True):
        resp = await client.get(
            f"/findings/{finding.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text

        # Same call as admin → 200
        admin_token = _user_token("root", "admin")
        resp = await client.get(
            f"/findings/{finding.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

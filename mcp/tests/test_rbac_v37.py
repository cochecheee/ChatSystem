"""V3.7 RBAC tests — closes run-scoped + global-stats gaps found in the
phân-quyền audit.

Gaps closed:
  1. GET  /github/runs/{run_id}/findings   — was authed but unscoped.
  2. GET  /github/runs/{run_id}/artifacts  — was authed but unscoped.
  3. POST /github/runs/{run_id}/reprocess  — had NO auth at all (destructive).
  4. GET  /stats/overview (no project_id)  — leaked cross-project aggregates
     to non-admin members; now scoped to the caller's memberships.

A run maps 1:1 to a project via its Artifact rows, so a non-admin must be a
member of that project to read its findings/artifacts or reprocess it.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.auth import create_access_token


def _tok(username: str, role: str, memberships: dict | None = None) -> str:
    return create_access_token(username, role, memberships=memberships)


def _rbac_on():
    return (
        patch("src.core.config.settings.ANONYMOUS_READ_ENABLED", False),
        patch("src.core.config.settings.RBAC_PER_PROJECT", True),
    )


@pytest.fixture
async def run_in_b(client, db_session):
    """Two projects; an ingested run (id 999001) with a finding under project B."""
    a = (await client.post("/projects", json={
        "name": "A", "github_url": "https://github.com/t/a"})).json()
    b = (await client.post("/projects", json={
        "name": "B", "github_url": "https://github.com/t/b"})).json()
    from src.models.entities import Artifact, Finding

    art = Artifact(
        github_artifact_id="art-b", project_id=b["id"],
        github_run_id=999001, status="processed",
    )
    db_session.add(art)
    await db_session.flush()
    db_session.add(Finding(
        artifact_id=art.id, tool="trivy", rule_id="CVE-x",
        severity="high", message="m", file_path="r.txt",
    ))
    await db_session.commit()
    return a, b, 999001


@pytest.mark.asyncio
async def test_run_findings_blocked_cross_project(client, run_in_b):
    a, b, run = run_in_b
    anon, rbac = _rbac_on()
    with anon, rbac:
        # dev_a (member of A only) → 403 on B's run findings
        ta = _tok("dev_a", "developer", {a["id"]: "developer"})
        r = await client.get(f"/github/runs/{run}/findings",
                             headers={"Authorization": f"Bearer {ta}"})
        assert r.status_code == 403, r.text
        # dev_b (member of B) → 200
        tb = _tok("dev_b", "developer", {b["id"]: "developer"})
        r2 = await client.get(f"/github/runs/{run}/findings",
                              headers={"Authorization": f"Bearer {tb}"})
        assert r2.status_code == 200, r2.text
        assert len(r2.json()) == 1
        # admin → 200
        r3 = await client.get(f"/github/runs/{run}/findings",
                              headers={"Authorization": f"Bearer {_tok('root', 'admin')}"})
        assert r3.status_code == 200


@pytest.mark.asyncio
async def test_run_artifacts_blocked_cross_project(client, run_in_b):
    a, b, run = run_in_b
    anon, rbac = _rbac_on()
    with anon, rbac:
        ta = _tok("dev_a", "developer", {a["id"]: "developer"})
        r = await client.get(f"/github/runs/{run}/artifacts",
                             headers={"Authorization": f"Bearer {ta}"})
        # 403 raised by the membership gate BEFORE any GitHub call.
        assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_reprocess_requires_membership(client, run_in_b):
    a, b, run = run_in_b
    anon, rbac = _rbac_on()
    with anon, rbac:
        # member of A → 403 on B's run
        ta = _tok("dev_a", "developer", {a["id"]: "developer"})
        r = await client.post(f"/github/runs/{run}/reprocess",
                              headers={"Authorization": f"Bearer {ta}"})
        assert r.status_code == 403, r.text
        # viewer of B → 403 (reprocess needs developer+)
        tv = _tok("view_b", "developer", {b["id"]: "viewer"})
        r2 = await client.post(f"/github/runs/{run}/reprocess",
                               headers={"Authorization": f"Bearer {tv}"})
        assert r2.status_code == 403, r2.text


@pytest.mark.asyncio
async def test_reprocess_unauthenticated_blocked_when_anon_off(client, run_in_b):
    _a, _b, run = run_in_b
    anon, rbac = _rbac_on()
    with anon, rbac:
        r = await client.post(f"/github/runs/{run}/reprocess")
        assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_stats_overview_global_scoped_to_memberships(client, db_session):
    """Non-admin with no project_id must see only their projects' aggregate,
    not the whole system."""
    a = (await client.post("/projects", json={
        "name": "A", "github_url": "https://github.com/t/a2"})).json()
    b = (await client.post("/projects", json={
        "name": "B", "github_url": "https://github.com/t/b2"})).json()
    from src.models.entities import Artifact, Finding

    arta = Artifact(github_artifact_id="aa", project_id=a["id"], status="processed")
    db_session.add(arta)
    await db_session.flush()
    db_session.add(Finding(artifact_id=arta.id, tool="t", rule_id="r",
                           severity="high", message="m", file_path="f"))
    artb = Artifact(github_artifact_id="bb", project_id=b["id"], status="processed")
    db_session.add(artb)
    await db_session.flush()
    db_session.add(Finding(artifact_id=artb.id, tool="t", rule_id="r",
                           severity="high", message="m", file_path="f"))
    db_session.add(Finding(artifact_id=artb.id, tool="t", rule_id="r2",
                           severity="critical", message="m", file_path="f"))
    await db_session.commit()

    anon, rbac = _rbac_on()
    with anon, rbac:
        # dev_a (member of A only) → global overview shows ONLY A's 1 finding
        ta = _tok("dev_a", "developer", {a["id"]: "developer"})
        r = await client.get("/stats/overview", headers={"Authorization": f"Bearer {ta}"})
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 1
        # admin → sees all 3
        r2 = await client.get("/stats/overview",
                              headers={"Authorization": f"Bearer {_tok('root', 'admin')}"})
        assert r2.json()["total"] == 3

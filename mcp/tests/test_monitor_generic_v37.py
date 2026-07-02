"""V3.7 — Monitor generic-hoá: uptime targets lấy per-project (Project.staging_url)
thay vì hardcode env MONITOR_TARGETS. Bất kỳ project tích hợp sast-action nào
set staging_url đều được giám sát tự động.
"""
from __future__ import annotations

import pytest

from src.core.auth import create_access_token


@pytest.mark.asyncio
async def test_gather_targets_picks_active_projects_with_staging_url(client, db_session):
    from src.models.entities import Project
    from src.services.monitor import _gather_targets

    db_session.add(Project(
        name="has-url", github_url="https://github.com/t/a",
        staging_url="https://a.example.com/health", active=1,
    ))
    db_session.add(Project(  # no staging_url → bỏ qua
        name="no-url", github_url="https://github.com/t/b",
        staging_url="", active=1,
    ))
    db_session.add(Project(  # inactive → list_active bỏ qua
        name="inactive", github_url="https://github.com/t/c",
        staging_url="https://c.example.com/health", active=0,
    ))
    await db_session.commit()

    targets = await _gather_targets()
    urls = {u for _pid, u in targets}
    assert "https://a.example.com/health" in urls
    assert "https://c.example.com/health" not in urls   # inactive
    assert "" not in urls                                # empty staging_url


@pytest.mark.asyncio
async def test_create_project_with_staging_url(client, admin_headers):
    resp = await client.post("/projects", json={
        "name": "P", "github_url": "https://github.com/t/create",
        "staging_url": "https://p.example.com/health",
    }, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["staging_url"] == "https://p.example.com/health"


@pytest.mark.asyncio
async def test_patch_monitor_target(client):
    tok = create_access_token("root", "admin")
    proj = (await client.post("/projects", json={
        "name": "P2", "github_url": "https://github.com/t/patch"},
        headers={"Authorization": f"Bearer {tok}"})).json()

    r = await client.patch(
        f"/projects/{proj['id']}/monitor",
        json={"staging_url": "https://p2.example.com/health"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["monitored"] is True
    assert r.json()["staging_url"] == "https://p2.example.com/health"

    # reflected in /projects output
    lst = (await client.get("/projects", headers={"Authorization": f"Bearer {tok}"})).json()
    assert any(p.get("staging_url") == "https://p2.example.com/health" for p in lst)

    # clear it
    r2 = await client.patch(
        f"/projects/{proj['id']}/monitor", json={"staging_url": ""},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r2.json()["monitored"] is False


@pytest.mark.asyncio
async def test_patch_monitor_rejects_bad_url(client):
    tok = create_access_token("root", "admin")
    proj = (await client.post("/projects", json={
        "name": "P3", "github_url": "https://github.com/t/badurl"},
        headers={"Authorization": f"Bearer {tok}"})).json()
    r = await client.patch(
        f"/projects/{proj['id']}/monitor", json={"staging_url": "not-a-url"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 400, r.text

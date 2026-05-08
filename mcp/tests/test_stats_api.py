"""Tests for stats endpoints (Wave 5 — GAP-1, GAP-2)."""
import pytest

from src.models.entities import Artifact, Finding, Project


@pytest.mark.asyncio
async def test_stats_overview_empty_db(client):
    resp = await client.get("/stats/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["critical_high"] == 0
    assert body["ai_analyzed"] == 0
    assert body["ai_analyzed_pct"] == 0
    assert body["by_severity"] == {}


@pytest.mark.asyncio
async def test_stats_overview_with_findings(client, db_session):
    p = Project(name="P", github_url="https://github.com/a/b")
    db_session.add(p)
    await db_session.flush()
    a = Artifact(github_artifact_id="x", project_id=p.id, status="processed")
    db_session.add(a)
    await db_session.flush()

    f1 = Finding(artifact_id=a.id, tool="semgrep", rule_id="r1", severity="critical",
                 message="m", file_path="f.py", status="pending_review")
    f2 = Finding(artifact_id=a.id, tool="codeql", rule_id="r2", severity="high",
                 message="m", file_path="f.py", status="ai_analyzed",
                 ai_analysis={"foo": "bar"})
    f3 = Finding(artifact_id=a.id, tool="semgrep", rule_id="r3", severity="low",
                 message="m", file_path="f.py", status="APPROVED")
    db_session.add_all([f1, f2, f3])
    await db_session.commit()

    resp = await client.get("/stats/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["critical_high"] == 2
    assert body["ai_analyzed"] == 1
    assert body["by_severity"]["critical"] == 1
    assert body["by_severity"]["high"] == 1
    assert body["by_severity"]["low"] == 1
    assert body["by_tool"]["semgrep"] == 2
    assert body["approved"] == 1
    assert body["open"] == 2  # total 3 - approved 1 - revoked 0


@pytest.mark.asyncio
async def test_stats_runs_handles_no_github(client):
    """Khi GitHub không configured, endpoint không crash — trả empty stats."""
    resp = await client.get("/stats/runs?days=7")
    assert resp.status_code == 200
    body = resp.json()
    assert body["days"] == 7
    assert "total" in body
    assert "by_conclusion" in body


@pytest.mark.asyncio
async def test_latest_scan_empty_db(client):
    resp = await client.get("/stats/latest-scan")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] is None
    assert body["total"] == 0
    assert body["by_severity"] == {}


@pytest.mark.asyncio
async def test_latest_scan_returns_most_recent_run(client, db_session):
    p = Project(name="P", github_url="https://github.com/x/y")
    db_session.add(p)
    await db_session.flush()

    # Old run (artifact created earlier)
    a_old = Artifact(github_artifact_id="old", project_id=p.id, github_run_id=100, status="processed")
    db_session.add(a_old)
    await db_session.flush()
    db_session.add(Finding(
        artifact_id=a_old.id, tool="trivy", rule_id="r1", severity="high",
        message="old", file_path="a.py", status="pending_review",
    ))
    # New run
    a_new = Artifact(github_artifact_id="new", project_id=p.id, github_run_id=200, status="processed")
    db_session.add(a_new)
    await db_session.flush()
    db_session.add_all([
        Finding(artifact_id=a_new.id, tool="trivy", rule_id="r2", severity="critical",
                message="new1", file_path="b.py", status="pending_review"),
        Finding(artifact_id=a_new.id, tool="trivy", rule_id="r3", severity="medium",
                message="new2", file_path="b.py", status="ai_analyzed",
                ai_analysis={"x": 1}),
    ])
    await db_session.commit()

    resp = await client.get("/stats/latest-scan")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == 200  # New run picked, không phải old
    assert body["total"] == 2
    assert body["critical_high"] == 1
    assert body["ai_analyzed"] == 1
    assert body["ai_analyzed_pct"] == 50.0
    assert body["by_severity"]["critical"] == 1
    assert body["by_severity"]["medium"] == 1

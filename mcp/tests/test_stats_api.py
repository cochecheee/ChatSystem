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
    a = Artifact(github_artifact_id="x", project_id=p.id, github_run_id=1, status="processed")
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


@pytest.mark.asyncio
async def test_overview_and_list_scope_to_latest_run(client, db_session):
    """V3.8 — CI chạy lại nhân bản findings qua các run. Overview + list phải
    chỉ tính run MỚI NHẤT (current-state), không cộng dồn run cũ."""
    p = Project(name="P", github_url="https://github.com/x/z")
    db_session.add(p)
    await db_session.flush()

    # Run cũ (flush trước → created_at sớm hơn): 1 high
    a_old = Artifact(github_artifact_id="o", project_id=p.id, github_run_id=100, status="processed")
    db_session.add(a_old)
    await db_session.flush()
    db_session.add(Finding(artifact_id=a_old.id, tool="trivy", rule_id="old", severity="high",
                           message="m", file_path="a.py", status="pending_review"))
    # Run mới: 1 critical + 1 medium (cùng codebase, re-scan)
    a_new = Artifact(github_artifact_id="n", project_id=p.id, github_run_id=200, status="processed")
    db_session.add(a_new)
    await db_session.flush()
    db_session.add_all([
        Finding(artifact_id=a_new.id, tool="trivy", rule_id="new1", severity="critical",
                message="m", file_path="b.py", status="pending_review"),
        Finding(artifact_id=a_new.id, tool="trivy", rule_id="new2", severity="medium",
                message="m", file_path="b.py", status="pending_review"),
    ])
    await db_session.commit()

    # Overview: chỉ run mới nhất (200) → total 2, critical_high 1 (KHÔNG +1 high của run cũ)
    ov = (await client.get(f"/stats/overview?project_id={p.id}")).json()
    assert ov["total"] == 2, ov
    assert ov["critical_high"] == 1, ov

    # List: latest_run_only=true → chỉ 2 finding của run 200
    lst = (await client.get(f"/findings?project_id={p.id}&latest_run_only=true")).json()
    assert len(lst) == 2
    # Không bật cờ → thấy cả 3 (lịch sử mọi run)
    allruns = (await client.get(f"/findings?project_id={p.id}")).json()
    assert len(allruns) == 3


# V2.9 — multi-project filtering on /stats endpoints


@pytest.mark.asyncio
async def test_stats_overview_filters_by_project_id(client, db_session):
    """`?project_id=` chỉ tính findings của project đó."""
    p1 = Project(name="P1", github_url="https://github.com/a/b")
    p2 = Project(name="P2", github_url="https://github.com/c/d")
    db_session.add_all([p1, p2])
    await db_session.flush()

    a1 = Artifact(github_artifact_id="a1", project_id=p1.id, github_run_id=1, status="processed")
    a2 = Artifact(github_artifact_id="a2", project_id=p2.id, github_run_id=2, status="processed")
    db_session.add_all([a1, a2])
    await db_session.flush()

    db_session.add_all([
        Finding(artifact_id=a1.id, tool="semgrep", rule_id="r1", severity="critical",
                message="m", file_path="f.py", status="pending_review"),
        Finding(artifact_id=a1.id, tool="codeql", rule_id="r2", severity="high",
                message="m", file_path="f.py", status="pending_review"),
        Finding(artifact_id=a2.id, tool="trivy", rule_id="r3", severity="medium",
                message="m", file_path="g.py", status="pending_review"),
    ])
    await db_session.commit()

    # Aggregate toàn bộ
    full = (await client.get("/stats/overview")).json()
    assert full["total"] == 3

    # Filter P1
    only_p1 = (await client.get(f"/stats/overview?project_id={p1.id}")).json()
    assert only_p1["total"] == 2
    assert only_p1["critical_high"] == 2
    assert only_p1["by_tool"].get("trivy") is None

    # Filter P2
    only_p2 = (await client.get(f"/stats/overview?project_id={p2.id}")).json()
    assert only_p2["total"] == 1
    assert only_p2["critical_high"] == 0


@pytest.mark.asyncio
async def test_latest_scan_filters_by_project_id(client, db_session):
    """`?project_id=` trên /latest-scan chỉ pick run của project đó."""
    p1 = Project(name="P1", github_url="https://github.com/a/b")
    p2 = Project(name="P2", github_url="https://github.com/c/d")
    db_session.add_all([p1, p2])
    await db_session.flush()

    a1 = Artifact(github_artifact_id="a1", project_id=p1.id,
                  github_run_id=100, status="processed")
    a2 = Artifact(github_artifact_id="a2", project_id=p2.id,
                  github_run_id=200, status="processed")
    db_session.add_all([a1, a2])
    await db_session.flush()
    db_session.add_all([
        Finding(artifact_id=a1.id, tool="semgrep", rule_id="r1", severity="critical",
                message="m", file_path="f.py", status="pending_review"),
        Finding(artifact_id=a2.id, tool="trivy", rule_id="r2", severity="high",
                message="m", file_path="g.py", status="pending_review"),
    ])
    await db_session.commit()

    # P1 → run 100 (only P1 run)
    body_p1 = (await client.get(f"/stats/latest-scan?project_id={p1.id}")).json()
    assert body_p1["run_id"] == 100
    body_p2 = (await client.get(f"/stats/latest-scan?project_id={p2.id}")).json()
    assert body_p2["run_id"] == 200

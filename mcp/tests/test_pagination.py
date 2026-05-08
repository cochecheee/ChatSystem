"""Tests for pagination + new filter params (Wave 1 + Wave 5 GAP-3)."""
import pytest

from src.models.entities import Artifact, Finding, Project


@pytest.mark.asyncio
async def test_findings_x_total_count_header(client, db_session):
    p = Project(name="P", github_url="https://github.com/x/y")
    db_session.add(p)
    await db_session.flush()
    a = Artifact(github_artifact_id="g", project_id=p.id, status="processed")
    db_session.add(a)
    await db_session.flush()

    for i in range(5):
        db_session.add(Finding(
            artifact_id=a.id, tool="semgrep", rule_id=f"r{i}", severity="medium",
            message=f"msg-{i}", file_path=f"f{i}.py", status="pending_review",
        ))
    await db_session.commit()

    resp = await client.get("/findings?limit=2")
    assert resp.status_code == 200
    assert resp.headers["x-total-count"] == "5"
    body = resp.json()
    assert len(body) == 2


@pytest.mark.asyncio
async def test_findings_filter_by_tool(client, db_session):
    p = Project(name="P2", github_url="https://github.com/x/z")
    db_session.add(p)
    await db_session.flush()
    a = Artifact(github_artifact_id="g2", project_id=p.id, status="processed")
    db_session.add(a)
    await db_session.flush()
    db_session.add_all([
        Finding(artifact_id=a.id, tool="semgrep", rule_id="r1", severity="high",
                message="m", file_path="f.py", status="pending_review"),
        Finding(artifact_id=a.id, tool="codeql", rule_id="r2", severity="high",
                message="m", file_path="f.py", status="pending_review"),
    ])
    await db_session.commit()

    resp = await client.get("/findings?tool=codeql")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["tool"] == "codeql"


@pytest.mark.asyncio
async def test_findings_filter_by_status(client, db_session):
    p = Project(name="P3", github_url="https://github.com/x/w")
    db_session.add(p)
    await db_session.flush()
    a = Artifact(github_artifact_id="g3", project_id=p.id, status="processed")
    db_session.add(a)
    await db_session.flush()
    db_session.add_all([
        Finding(artifact_id=a.id, tool="t", rule_id="r1", severity="high",
                message="m", file_path="f.py", status="pending_review"),
        Finding(artifact_id=a.id, tool="t", rule_id="r2", severity="high",
                message="m", file_path="f.py", status="APPROVED"),
    ])
    await db_session.commit()

    resp = await client.get("/findings?status=APPROVED")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_findings_filter_by_category(client, db_session):
    p = Project(name="P4", github_url="https://github.com/x/v")
    db_session.add(p)
    await db_session.flush()
    a = Artifact(github_artifact_id="g4", project_id=p.id, status="processed")
    db_session.add(a)
    await db_session.flush()
    db_session.add_all([
        Finding(artifact_id=a.id, tool="semgrep", rule_id="r1", severity="high",
                message="m", file_path="f.py", status="pending_review"),
        Finding(artifact_id=a.id, tool="dependency-check", rule_id="CVE-1", severity="high",
                message="m", file_path="pom.xml", status="pending_review"),
    ])
    await db_session.commit()

    resp = await client.get("/findings?category=sast")
    assert len(resp.json()) == 1
    assert resp.json()[0]["tool"] == "semgrep"

    resp = await client.get("/findings?category=deps")
    assert len(resp.json()) == 1
    assert resp.json()[0]["tool"] == "dependency-check"


@pytest.mark.asyncio
async def test_findings_search_q(client, db_session):
    p = Project(name="P5", github_url="https://github.com/x/u")
    db_session.add(p)
    await db_session.flush()
    a = Artifact(github_artifact_id="g5", project_id=p.id, status="processed")
    db_session.add(a)
    await db_session.flush()
    db_session.add_all([
        Finding(artifact_id=a.id, tool="t", rule_id="sql-injection", severity="high",
                message="possible SQL", file_path="api.py", status="pending_review"),
        Finding(artifact_id=a.id, tool="t", rule_id="xss", severity="medium",
                message="reflected XSS", file_path="view.py", status="pending_review"),
    ])
    await db_session.commit()

    # Match rule_id
    resp = await client.get("/findings?q=sql")
    assert len(resp.json()) == 1
    assert resp.json()[0]["rule_id"] == "sql-injection"

    # Match message
    resp = await client.get("/findings?q=xss")
    assert len(resp.json()) == 1
    assert resp.json()[0]["rule_id"] == "xss"

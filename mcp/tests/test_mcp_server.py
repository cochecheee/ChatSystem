"""Tests cho MCP server tools (V2.7 / báo cáo tiến độ ch.3.2).

Gọi mcp.call_tool() trực tiếp, không qua stdio/HTTP transport — đủ để
verify wiring + DB integration. Live transport verify dùng `mcp` CLI
Inspector ở docs/mcp-server.md.
"""
import uuid

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def seeded_finding(client):
    """Tạo Project + Artifact + Finding để test list/get/approve/explain.

    Phụ thuộc `client` fixture — fixture đó reset DB qua drop_all/create_all
    và init_db().
    """
    from src.core.db import AsyncSessionLocal
    from src.models.entities import Artifact, Finding, Project

    async with AsyncSessionLocal() as session:
        project = Project(
            name=f"MCP-test {uuid.uuid4().hex[:6]}",
            github_url=f"https://github.com/test/{uuid.uuid4().hex}",
        )
        session.add(project)
        await session.flush()

        artifact = Artifact(
            github_artifact_id="mcp-test-art",
            project_id=project.id,
            status="processed",
        )
        session.add(artifact)
        await session.flush()

        finding = Finding(
            artifact_id=artifact.id,
            tool="semgrep",
            rule_id="java.sql-injection",
            severity="high",
            message="Potential SQL injection — string concat",
            file_path="src/UserDao.java",
            line_number=42,
            status="pending_review",
        )
        session.add(finding)
        await session.commit()
        await session.refresh(finding)
        return finding.id


# ---------------------------------------------------------------------------
# Tool surface
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_tools_includes_eight(client):
    """8 tool tối thiểu theo plan V2.7."""
    from src.mcp_server import mcp

    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert {
        "list_findings", "get_finding", "explain_finding",
        "approve_finding", "revoke_finding",
        "list_pipelines", "get_stats_overview", "trigger_scan",
    } <= names


@pytest.mark.asyncio
async def test_list_findings_empty_db(client):
    from src.mcp_server import mcp

    result = await mcp.call_tool("list_findings", {})
    data = result.structured_content
    assert data["total_matching"] == 0
    assert data["returned"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_findings_returns_seeded(client, seeded_finding):
    from src.mcp_server import mcp

    result = await mcp.call_tool("list_findings", {"limit": 10})
    data = result.structured_content
    assert data["returned"] >= 1
    found = next((f for f in data["items"] if f["id"] == seeded_finding), None)
    assert found is not None
    assert found["tool"] == "semgrep"
    assert found["severity"] == "high"


@pytest.mark.asyncio
async def test_list_findings_severity_filter(client, seeded_finding):
    from src.mcp_server import mcp

    result = await mcp.call_tool("list_findings", {"severity": "high"})
    data = result.structured_content
    assert all(f["severity"] == "high" for f in data["items"])

    result_low = await mcp.call_tool("list_findings", {"severity": "low"})
    assert result_low.structured_content["returned"] == 0


@pytest.mark.asyncio
async def test_get_finding_found(client, seeded_finding):
    from src.mcp_server import mcp

    result = await mcp.call_tool("get_finding", {"finding_id": seeded_finding})
    data = result.structured_content
    assert data["id"] == seeded_finding
    assert data["status"] == "pending_review"


@pytest.mark.asyncio
async def test_get_finding_not_found(client):
    from src.mcp_server import mcp

    result = await mcp.call_tool("get_finding", {"finding_id": 99999})
    assert result.structured_content["error"] == "not_found"


# ---------------------------------------------------------------------------
# Approve / revoke — share audit-trail logic with CommandService
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_approve_persists_audit(client, seeded_finding):
    from src.core.db import AsyncSessionLocal
    from src.mcp_server import mcp
    from src.repositories import FindingRepository

    result = await mcp.call_tool(
        "approve_finding",
        {
            "finding_id": seeded_finding,
            "justification": "False positive — validated upstream by SecurityFilter class",
        },
    )
    data = result.structured_content
    assert data["status"] == "ok"
    assert data["data"]["approved_by"] == "mcp:security_lead"

    async with AsyncSessionLocal() as session:
        f = await FindingRepository(session).get(seeded_finding)
        assert f.status == "APPROVED"
        assert f.approved_by == "mcp:security_lead"


@pytest.mark.asyncio
async def test_approve_short_justification_errors(client, seeded_finding):
    from src.mcp_server import mcp

    result = await mcp.call_tool(
        "approve_finding",
        {"finding_id": seeded_finding, "justification": "too short"},
    )
    data = result.structured_content
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_revoke_after_approve(client, seeded_finding):
    from src.mcp_server import mcp

    await mcp.call_tool(
        "approve_finding",
        {
            "finding_id": seeded_finding,
            "justification": "False positive — validated upstream by SecurityFilter",
        },
    )
    result = await mcp.call_tool(
        "revoke_finding",
        {
            "finding_id": seeded_finding,
            "justification": "Recent evidence shows the upstream filter can be bypassed",
        },
    )
    data = result.structured_content
    assert data["status"] == "ok"
    assert data["data"]["revoked_by"] == "mcp:security_lead"


@pytest.mark.asyncio
async def test_unrevoke_finding_restores_pending(client, seeded_finding):
    from src.mcp_server import mcp

    await mcp.call_tool(
        "revoke_finding",
        {
            "finding_id": seeded_finding,
            "justification": "Marking false positive before testing the unrevoke tool",
        },
    )
    result = await mcp.call_tool("unrevoke_finding", {"finding_id": seeded_finding})
    data = result.structured_content
    assert data["status"] == "ok"
    assert data["data"]["status"] == "pending_review"

    from src.core.db import AsyncSessionLocal
    from src.models.entities import Finding
    async with AsyncSessionLocal() as s:
        f = await s.get(Finding, seeded_finding)
        assert f.status == "pending_review"
        assert f.revoked_by is None


# ---------------------------------------------------------------------------
# Stats / pipelines / trigger — wrap existing services
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stats_overview_shape(client, seeded_finding):
    from src.mcp_server import mcp

    result = await mcp.call_tool("get_stats_overview", {})
    data = result.structured_content
    # Same shape as StatsService.overview()
    for key in ("total", "critical_high", "ai_analyzed", "by_severity", "by_tool"):
        assert key in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_list_pipelines_handles_github_error(client, monkeypatch):
    from src.mcp_server import mcp
    from src.services import github_client as gh_mod

    async def boom(*args, **kwargs):
        raise RuntimeError("github down")

    monkeypatch.setattr(gh_mod.GitHubClient, "list_workflow_runs", boom)
    result = await mcp.call_tool("list_pipelines", {})
    assert result.structured_content["error"] == "github_unreachable"


@pytest.mark.asyncio
async def test_trigger_scan_handles_github_error(client, monkeypatch):
    from src.mcp_server import mcp
    from src.services import github_client as gh_mod

    async def boom(*args, **kwargs):
        raise RuntimeError("dispatch denied")

    monkeypatch.setattr(gh_mod.GitHubClient, "dispatch_workflow", boom)
    result = await mcp.call_tool("trigger_scan", {})
    assert result.structured_content["status"] == "error"


@pytest.mark.asyncio
async def test_trigger_scan_success(client, monkeypatch):
    from src.mcp_server import mcp
    from src.services import github_client as gh_mod

    called = []

    async def fake_dispatch(self, workflow_filename, ref="main"):
        called.append((workflow_filename, ref))

    monkeypatch.setattr(gh_mod.GitHubClient, "dispatch_workflow", fake_dispatch)
    result = await mcp.call_tool("trigger_scan", {"workflow_filename": "ci.yml"})
    data = result.structured_content
    assert data["status"] == "ok"
    assert data["workflow"] == "ci.yml"
    assert called == [("ci.yml", "main")]

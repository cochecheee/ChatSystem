"""Tests for Phase 6: ChatOps command API and auth."""
import uuid

import pytest
import pytest_asyncio

from src.core.auth import create_access_token


def _token(role: str = "developer", username: str | None = None) -> str:
    return create_access_token(username=username or f"user_{role}", role=role)


def _headers(role: str = "developer") -> dict:
    return {"Authorization": f"Bearer {_token(role)}"}


# ---------------------------------------------------------------------------
# Auth — demo login
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_demo_login_returns_token(client):
    resp = await client.post("/api/chat/auth/token", json={"username": "alice", "role": "developer"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_demo_login_invalid_role(client):
    resp = await client.post("/api/chat/auth/token", json={"username": "bob", "role": "superadmin"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_command_no_token_returns_401(client):
    resp = await client.post("/api/chat/command", json={"command": "/explain", "finding_id": 1})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Unknown command
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_command_returns_400(client):
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/hack"},
        headers=_headers("admin"),
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Role enforcement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_developer_cannot_approve(client):
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/approve", "finding_id": 1, "justification": "some justification text here"},
        headers=_headers("developer"),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_developer_cannot_scan(client):
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/scan"},
        headers=_headers("developer"),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_developer_cannot_rerun(client):
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/rerun", "run_id": 123},
        headers=_headers("developer"),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# /approve and /revoke business logic
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def finding_id(client):
    """Create project + artifact + finding directly in DB, return finding id."""
    from src.core.db import AsyncSessionLocal
    from src.models.entities import Artifact, Finding, Project

    async with AsyncSessionLocal() as session:
        project = Project(
            name=f"ChatTest {uuid.uuid4().hex[:6]}",
            github_url=f"https://github.com/test/{uuid.uuid4().hex}",
        )
        session.add(project)
        await session.flush()

        artifact = Artifact(
            github_artifact_id="test-artifact",
            project_id=project.id,
            status="processed",
        )
        session.add(artifact)
        await session.flush()

        finding = Finding(
            artifact_id=artifact.id,
            tool="semgrep",
            rule_id="java.sql-injection",
            severity="HIGH",
            message="Potential SQL injection",
            file_path="src/UserDao.java",
            line_number=42,
            status="pending_review",
        )
        session.add(finding)
        await session.commit()
        await session.refresh(finding)
        return finding.id


@pytest.mark.asyncio
async def test_approve_finding(client, finding_id):
    resp = await client.post(
        "/api/chat/command",
        json={
            "command": "/approve",
            "finding_id": finding_id,
            "justification": "False positive — input is validated upstream by SecurityFilter",
        },
        headers=_headers("security_lead"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "phê duyệt" in body["message"]
    assert body["data"]["approved_by"] == "user_security_lead"


@pytest.mark.asyncio
async def test_approve_already_approved(client, finding_id):
    justification = "False positive — validated by SecurityFilter class"
    headers = _headers("security_lead")
    await client.post(
        "/api/chat/command",
        json={"command": "/approve", "finding_id": finding_id, "justification": justification},
        headers=headers,
    )
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/approve", "finding_id": finding_id, "justification": justification},
        headers=headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_approve_short_justification(client, finding_id):
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/approve", "finding_id": finding_id, "justification": "Too short"},
        headers=_headers("security_lead"),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_approve_nonexistent_finding(client):
    resp = await client.post(
        "/api/chat/command",
        json={
            "command": "/approve",
            "finding_id": 99999,
            "justification": "Some valid justification text that is long enough",
        },
        headers=_headers("security_lead"),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_revoke_finding(client, finding_id):
    # First approve
    await client.post(
        "/api/chat/command",
        json={
            "command": "/approve",
            "finding_id": finding_id,
            "justification": "False positive — input is validated upstream",
        },
        headers=_headers("security_lead"),
    )
    # Then revoke
    resp = await client.post(
        "/api/chat/command",
        json={
            "command": "/revoke",
            "finding_id": finding_id,
            "justification": "New evidence shows this is actually exploitable via X",
        },
        headers=_headers("security_lead"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "thu hồi" in body["message"]


@pytest.mark.asyncio
async def test_revoke_already_revoked(client, finding_id):
    justification = "New evidence shows this is actually exploitable via X"
    headers = _headers("security_lead")
    await client.post(
        "/api/chat/command",
        json={"command": "/revoke", "finding_id": finding_id, "justification": justification},
        headers=headers,
    )
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/revoke", "finding_id": finding_id, "justification": justification},
        headers=headers,
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# /report
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_report_download(client):
    resp = await client.get("/api/chat/report", headers=_headers("developer"))
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "security-report.html" in resp.headers.get("content-disposition", "")
    assert b"Sentinel SAST" in resp.content


# ---------------------------------------------------------------------------
# /help, /feedback, /results, /status — báo cáo tiến độ docx ch.4.3
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_help_lists_ten_commands(client):
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/help"},
        headers=_headers("developer"),
    )
    assert resp.status_code == 200
    body = resp.json()
    cmds = body["data"]["commands"]
    names = {c["name"] for c in cmds}
    # All 10 commands from docx ch.4.3 + /revoke (project addition)
    assert {"/status", "/scan", "/results", "/explain", "/fix", "/rerun",
            "/approve", "/revoke", "/report", "/help", "/feedback"} <= names
    assert body["data"]["current_role"] == "developer"


@pytest.mark.asyncio
async def test_feedback_requires_text(client):
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/feedback"},
        headers=_headers("developer"),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_feedback_persists(client, finding_id):
    resp = await client.post(
        "/api/chat/command",
        json={
            "command": "/feedback",
            "finding_id": finding_id,
            "feedback_text": "Suggestion was helpful, fixed in PR #42",
        },
        headers=_headers("developer"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["feedback_id"] > 0
    assert body["data"]["finding_id"] == finding_id


@pytest.mark.asyncio
async def test_feedback_unknown_finding(client):
    resp = await client.post(
        "/api/chat/command",
        json={
            "command": "/feedback",
            "finding_id": 99999,
            "feedback_text": "Note about non-existent finding",
        },
        headers=_headers("developer"),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_results_empty_db(client):
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/results"},
        headers=_headers("developer"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["total"] == 0


@pytest.mark.asyncio
async def test_results_with_findings(client, finding_id):
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/results"},
        headers=_headers("developer"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["total"] >= 1
    assert "by_severity" in body["data"]


@pytest.mark.asyncio
async def test_results_unknown_run_id(client):
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/results", "run_id": 99999999},
        headers=_headers("developer"),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_status_developer_allowed(client, monkeypatch):
    # Avoid hitting real GitHub API in tests
    async def fake_list(*args, **kwargs):
        return []

    from src.services import command_service as cs_mod

    monkeypatch.setattr(cs_mod.GitHubClient, "list_workflow_runs", fake_list)
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/status"},
        headers=_headers("developer"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["runs"] == []

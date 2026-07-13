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
# Auth — password login (V3.8)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_returns_token(client):
    """Correct username + password → 200 with a bearer token."""
    from tests.conftest import TEST_PASSWORD, issue_token
    # issue_token seeds the user then logs in; assert the token is usable.
    token = await issue_token(client, "alice", role="developer")
    assert token
    resp = await client.post(
        "/api/chat/auth/token",
        json={"username": "alice", "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password_401(client):
    """Seeded user + wrong password → 401."""
    from tests.conftest import issue_token
    await issue_token(client, "alice", role="developer")  # seed
    resp = await client.post(
        "/api/chat/auth/token",
        json={"username": "alice", "password": "not-the-password"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user_401(client):
    """Unknown username → 401 (same as wrong password — no enumeration)."""
    resp = await client.post(
        "/api/chat/auth/token",
        json={"username": "ghost", "password": "whatever"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_role_from_db_not_request(client):
    """Role is read from the users table, not the request body (can't forge)."""
    import jose.jwt as jwt

    from src.core.config import settings
    from tests.conftest import TEST_PASSWORD, issue_token
    await issue_token(client, "alice", role="developer")  # seed as developer
    resp = await client.post(
        "/api/chat/auth/token",
        json={"username": "alice", "password": TEST_PASSWORD, "role": "admin"},
    )
    assert resp.status_code == 200
    payload = jwt.decode(resp.json()["access_token"], settings.SECRET_KEY, algorithms=["HS256"])
    assert payload["role"] == "developer"  # request's "admin" ignored


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
# /unrevoke — đảo ngược /revoke
# ---------------------------------------------------------------------------

async def _revoke(client, finding_id):
    return await client.post(
        "/api/chat/command",
        json={
            "command": "/revoke",
            "finding_id": finding_id,
            "justification": "Marking as false positive for unrevoke test scenario",
        },
        headers=_headers("security_lead"),
    )


@pytest.mark.asyncio
async def test_unrevoke_restores_pending(client, finding_id):
    """Revoke then unrevoke → finding returns to pending_review, audit fields cleared."""
    assert (await _revoke(client, finding_id)).status_code == 200

    resp = await client.post(
        "/api/chat/command",
        json={"command": "/unrevoke", "finding_id": finding_id},
        headers=_headers("security_lead"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"]["status"] == "pending_review"
    assert "khôi phục" in body["message"].lower()

    # Confirm DB state: status flipped, revoke fields cleared.
    from src.core.db import AsyncSessionLocal
    from src.models.entities import Finding
    async with AsyncSessionLocal() as s:
        f = await s.get(Finding, finding_id)
        assert f.status == "pending_review"
        assert f.revoked_by is None
        assert f.revoked_at is None
        assert f.revoke_justification is None


@pytest.mark.asyncio
async def test_unrevoke_not_revoked_409(client, finding_id):
    """Unrevoking a finding that isn't REVOKED → 409."""
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/unrevoke", "finding_id": finding_id},
        headers=_headers("security_lead"),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_unrevoke_requires_security_lead(client, finding_id):
    """A plain developer cannot unrevoke (role gate → 403)."""
    await _revoke(client, finding_id)
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/unrevoke", "finding_id": finding_id},
        headers=_headers("developer"),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unrevoke_nonexistent_404(client):
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/unrevoke", "finding_id": 99999},
        headers=_headers("security_lead"),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /report
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_report_download(client):
    resp = await client.get("/api/chat/report", headers=_headers("developer"))
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "security-report.html" in resp.headers.get("content-disposition", "")
    assert b"Shiftwall" in resp.content


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
    # All 10 commands from docx ch.4.3 + /revoke + /unrevoke (additions)
    assert {"/status", "/scan", "/results", "/explain", "/fix", "/rerun",
            "/approve", "/revoke", "/unrevoke", "/report", "/help", "/feedback"} <= names
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


# ---------------------------------------------------------------------------
# V4.3 — "lỗi này có thật không?" investigation (chat + /verify)
# ---------------------------------------------------------------------------

def test_investigation_intent_detection():
    from src.api.chat import _investigation_intent
    assert _investigation_intent("lỗi #3319 có thật không?") == 3319
    assert _investigation_intent("finding 42 có phải false positive?") == 42
    assert _investigation_intent("#7 kiểm chứng giúp") == 7
    # No FP-intent → None even with a number present
    assert _investigation_intent("giải thích finding 5") is None
    assert _investigation_intent("báo cáo tổng quan") is None


def _fake_investigation(verdict: str = "FALSE_POSITIVE"):
    from src.models.schemas import FPInvestigation, InvestigationStep

    async def fake(self, finding, session, force=False):
        return FPInvestigation(
            finding_id=finding.id, verdict=verdict, confidence="HIGH",
            summary_vi="Đây là false positive vì input đã được validate upstream.",
            steps=[InvestigationStep(
                claim_vi="input được validate trước sink", file="f.py",
                line_start=1, line_end=1, quote="if not valid: return", grounded=True,
            )],
            false_positive_likelihood="HIGH", grounded=True, grounded_note="1/1 khớp",
            source_available=True,
            suggested_command=(f"/revoke {finding.id}" if verdict == "FALSE_POSITIVE" else None),
        )
    return fake


@pytest.mark.asyncio
async def test_verify_command_returns_investigation(client, finding_id, monkeypatch):
    from src.services.llm.service import LLMAnalysisService
    monkeypatch.setattr(LLMAnalysisService, "investigate_finding", _fake_investigation())
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/verify", "finding_id": finding_id},
        headers=_headers("developer"),
    )
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["verdict"] == "FALSE_POSITIVE"
    assert d["suggested_command"] == f"/revoke {finding_id}"
    assert d["steps"][0]["grounded"] is True


@pytest.mark.asyncio
async def test_verify_command_forbidden_for_viewer(client, finding_id):
    resp = await client.post(
        "/api/chat/command",
        json={"command": "/verify", "finding_id": finding_id},
        headers=_headers("viewer"),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_chat_message_runs_investigation(client, finding_id, monkeypatch):
    from src.services.llm.service import LLMAnalysisService
    monkeypatch.setattr(LLMAnalysisService, "investigate_finding", _fake_investigation())
    resp = await client.post(
        "/api/chat/message",
        json={"text": f"lỗi #{finding_id} có thật không?"},
        headers=_headers("developer"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["investigation"] is not None
    assert body["investigation"]["verdict"] == "FALSE_POSITIVE"
    assert body["suggested_command"] == f"/revoke {finding_id}"

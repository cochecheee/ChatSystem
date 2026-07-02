"""Conformance to report §4.3.2 (10-turn chat state) and §4.3.3 (finding_actions)."""
from sqlalchemy import select

from src.api import chat as chat_mod
from src.core.auth import User
from src.core.db import AsyncSessionLocal
from src.models.entities import Artifact, Finding, FindingAction, Project
from src.models.schemas import CommandRequest
from src.services.command_service import CommandService


# ---------------------------------------------------------------- §4.3.3
async def test_approve_writes_finding_action(client):
    async with AsyncSessionLocal() as s:
        p = Project(name="P", github_url="https://github.com/x/y")
        s.add(p)
        await s.commit()
        await s.refresh(p)
        a = Artifact(github_artifact_id="1", project_id=p.id, github_run_id=1, status="processed")
        s.add(a)
        await s.commit()
        await s.refresh(a)
        f = Finding(artifact_id=a.id, project_id=p.id, tool="semgrep", rule_id="r",
                    severity="high", message="m", file_path="f.py", status="pending_review")
        s.add(f)
        await s.commit()
        await s.refresh(f)
        fid = f.id

    async with AsyncSessionLocal() as s:
        user = User(username="lead", role="admin")
        req = CommandRequest(command="/approve", finding_id=fid,
                             justification="Reviewed manually, safe in this context.")
        await CommandService()._handle_approve(req, user, s)

    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(FindingAction))).scalars().all()
    assert len(rows) == 1
    assert rows[0].action == "approve"
    assert rows[0].finding_id == fid
    assert rows[0].submitted_by == "dashboard:lead"


# ---------------------------------------------------------------- §4.3.2
async def test_chat_history_capped_at_10(client, admin_headers, monkeypatch):
    chat_mod._CHAT_HISTORY.clear()

    class _FakeGemini:
        async def chat(self, prompt: str, context: str = "") -> str:
            return "phản hồi test"

    monkeypatch.setattr(chat_mod, "_get_gemini", lambda: _FakeGemini())

    for i in range(12):
        r = await client.post(
            "/api/chat/message",
            json={"text": f"câu hỏi số {i}"},
            headers=admin_headers,
        )
        assert r.status_code == 200

    key = ("admin", None)
    assert key in chat_mod._CHAT_HISTORY
    assert len(chat_mod._CHAT_HISTORY[key]) == 10       # capped
    # oldest dropped: first stored turn is question #2 (0,1 evicted)
    assert chat_mod._CHAT_HISTORY[key][0]["user"] == "câu hỏi số 2"
    assert chat_mod._CHAT_HISTORY[key][-1]["user"] == "câu hỏi số 11"

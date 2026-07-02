"""Group A — code fixes bringing the implementation in line with báo cáo Ch.4:
  A1  github_client.fetch_artifact retries transient failures (3x, backoff)
  A3  CommandService.handle dispatch via match-case (unknown → 400)
  A4  finding_actions.submitted_by source prefix (dashboard:/mcp:)
  A5  GET /findings/{id}/explain/stream — SSE streaming of the AI explanation
"""
import io
import zipfile
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from src.core.db import AsyncSessionLocal
from src.models.entities import Artifact, Finding, FindingAction, Project


# --------------------------------------------------------------- A1
async def test_fetch_artifact_retries_transient(monkeypatch):
    from src.services import github_client as gc

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("out.json", '{"ok": 1}')
    zip_bytes = buf.getvalue()

    calls = {"n": 0}

    class _Resp:
        def __init__(self, status, content=b""):
            self.status_code = status
            self.content = content
            self._req = httpx.Request("GET", "http://x")

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "err", request=self._req,
                    response=httpx.Response(self.status_code, request=self._req),
                )

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            calls["n"] += 1
            return _Resp(503) if calls["n"] < 3 else _Resp(200, zip_bytes)

    monkeypatch.setattr(gc.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(gc.asyncio, "sleep", AsyncMock())  # skip real backoff

    client = gc.GitHubClient(token="t", owner="o", repo="r")
    files = await client.fetch_artifact(123)

    assert calls["n"] == 3                       # 2 failures + 1 success
    assert files and files[0]["filename"] == "out.json"


async def test_fetch_artifact_no_retry_on_404(monkeypatch):
    from src.services import github_client as gc

    calls = {"n": 0}

    class _Resp:
        status_code = 404

        def __init__(self):
            self._req = httpx.Request("GET", "http://x")

        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                "nf", request=self._req,
                response=httpx.Response(404, request=self._req),
            )

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            calls["n"] += 1
            return _Resp()

    monkeypatch.setattr(gc.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(gc.asyncio, "sleep", AsyncMock())

    client = gc.GitHubClient(token="t", owner="o", repo="r")
    with pytest.raises(httpx.HTTPStatusError):
        await client.fetch_artifact(1)
    assert calls["n"] == 1                        # 404 is not retried


# --------------------------------------------------------------- A3
async def test_handle_unknown_command_400(client):
    from fastapi import HTTPException

    from src.core.auth import User
    from src.models.schemas import CommandRequest
    from src.services.command_service import CommandService

    async with AsyncSessionLocal() as s:
        with pytest.raises(HTTPException) as ei:
            await CommandService().handle(
                "bogus", CommandRequest(command="/bogus"),
                User(username="x", role="admin"), s,
            )
    assert ei.value.status_code == 400


# --------------------------------------------------------------- A4
async def test_log_action_source_prefix(client):
    """dashboard user → dashboard:<name>; MCP user (mcp:<role>) kept verbatim."""
    from src.core.auth import User
    from src.services.command_service import CommandService

    async with AsyncSessionLocal() as s:
        await CommandService._log_action(
            s, action="approve", user=User(username="alice", role="admin"),
        )
        await CommandService._log_action(
            s, action="approve", user=User(username="mcp:security_lead", role="security_lead"),
        )

    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(FindingAction).order_by(FindingAction.id))).scalars().all()
    sources = [r.submitted_by for r in rows]
    assert "dashboard:alice" in sources
    assert "mcp:security_lead" in sources


# --------------------------------------------------------------- A5
async def test_explain_stream_sse(client, project):
    from src.api.analysis import get_llm_service
    from src.main import app
    from tests.conftest import issue_token

    async with AsyncSessionLocal() as s:
        a = Artifact(github_artifact_id="strm", project_id=project["id"],
                     github_run_id=1, status="processed")
        s.add(a); await s.commit(); await s.refresh(a)
        f = Finding(artifact_id=a.id, project_id=project["id"], tool="semgrep",
                    rule_id="r", severity="high", message="m", file_path="f.py",
                    status="pending_review")
        s.add(f); await s.commit(); await s.refresh(f)
        fid = f.id

    class _FakeService:
        async def stream_explain(self, finding, session):
            for c in ["Đây ", "là ", "giải thích."]:
                yield c

    app.dependency_overrides[get_llm_service] = lambda: _FakeService()
    try:
        token = await issue_token(client, "tester", role="admin")
        resp = await client.get(
            f"/findings/{fid}/explain/stream",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = resp.text
        assert "giải thích." in body
        assert "event: done" in body
    finally:
        app.dependency_overrides.pop(get_llm_service, None)


async def test_explain_stream_cached_replays(client, project):
    """Already-analyzed finding replays cached explanation with no LLM call."""
    from src.services.llm.service import LLMAnalysisService

    async with AsyncSessionLocal() as s:
        a = Artifact(github_artifact_id="strm2", project_id=project["id"],
                     github_run_id=1, status="processed")
        s.add(a); await s.commit(); await s.refresh(a)
        f = Finding(artifact_id=a.id, project_id=project["id"], tool="semgrep",
                    rule_id="r", severity="high", message="m", file_path="f.py",
                    status="ai_analyzed",
                    ai_analysis={"explanation_vi": "kết quả cache", "severity": "HIGH"})
        s.add(f); await s.commit(); await s.refresh(f)

        chunks = [c async for c in LLMAnalysisService().stream_explain(f, s)]
    assert chunks == ["kết quả cache"]

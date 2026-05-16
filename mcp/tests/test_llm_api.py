from unittest.mock import AsyncMock, patch

import pytest

from src.api.analysis import get_llm_service
from src.models.schemas import AnalysisResult
from src.services.llm.service import LLMAnalysisService

SAMPLE_RESULT = AnalysisResult(
    finding_id=1,
    vulnerability_id="RULE-001",
    explanation_vi="Lỗ hổng SQL Injection.",
    impact_vi="Kẻ tấn công có thể truy cập database.",
    remediation_diff="--- a\n+++ b\n@@ -1 +1 @@\n-bad\n+good",
    severity="HIGH",
    cwe_reference="CWE-89",
    confidence="HIGH",
)


async def _auth_headers(client) -> dict[str, str]:
    """Helper — V3.2 BUG-3 made /findings/{id}/explain require authentication."""
    r = await client.post(
        "/api/chat/auth/token",
        json={"username": "tester", "role": "admin"},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_explain_finding_404_unknown(client):
    h = await _auth_headers(client)
    resp = await client.post("/findings/999999/explain", headers=h)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_explain_finding_returns_analysis(client, project):
    from src.main import app

    mock_service = AsyncMock(spec=LLMAnalysisService)
    mock_service.analyze_finding.return_value = SAMPLE_RESULT

    app.dependency_overrides[get_llm_service] = lambda: mock_service
    try:
        # create artifact + finding first via process endpoint
        from unittest.mock import patch as upatch
        from src.services.processor import SecurityProcessor

        with upatch.object(SecurityProcessor, "process_artifact", new_callable=AsyncMock, return_value=0):
            proc_resp = await client.post("/artifacts/process", json={
                "github_artifact_id": 9999,
                "project_id": project["id"],
            })
        assert proc_resp.status_code == 202
        artifact_id = proc_resp.json()["db_artifact_id"]

        # inject a finding directly via DB (easier than full pipeline)
        from src.core.db import AsyncSessionLocal
        from src.models.entities import Finding
        from datetime import datetime, UTC

        async with AsyncSessionLocal() as session:
            finding = Finding(
                artifact_id=artifact_id,
                tool="semgrep",
                rule_id="java.sqli",
                severity="high",
                message="SQL injection",
                file_path="src/Dao.java",
                line_number=10,
                status="pending_review",
            )
            session.add(finding)
            await session.commit()
            await session.refresh(finding)
            finding_id = finding.id

        h = await _auth_headers(client)
        resp = await client.post(f"/findings/{finding_id}/explain", headers=h)
        assert resp.status_code == 200
        data = resp.json()
        assert data["severity"] == "HIGH"
        assert "SQL" in data["explanation_vi"]
    finally:
        app.dependency_overrides.pop(get_llm_service, None)


@pytest.mark.asyncio
async def test_explain_finding_returns_cached_if_already_analyzed(client, project):
    from src.main import app
    from src.core.db import AsyncSessionLocal
    from src.models.entities import Artifact, Finding

    cached = SAMPLE_RESULT.model_dump()

    async with AsyncSessionLocal() as session:
        artifact = Artifact(
            github_artifact_id="cached-test",
            project_id=project["id"],
            status="processed",
        )
        session.add(artifact)
        await session.commit()
        await session.refresh(artifact)

        finding = Finding(
            artifact_id=artifact.id,
            tool="semgrep",
            rule_id="java.sqli",
            severity="high",
            message="SQL injection",
            file_path="src/Dao.java",
            line_number=5,
            status="ai_analyzed",
            ai_analysis=cached,
        )
        session.add(finding)
        await session.commit()
        await session.refresh(finding)
        finding_id = finding.id

    mock_service = AsyncMock(spec=LLMAnalysisService)
    app.dependency_overrides[get_llm_service] = lambda: mock_service
    try:
        h = await _auth_headers(client)
        resp = await client.post(f"/findings/{finding_id}/explain", headers=h)
        assert resp.status_code == 200
        mock_service.analyze_finding.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_llm_service, None)

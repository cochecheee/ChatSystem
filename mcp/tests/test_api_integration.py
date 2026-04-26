import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from src.api.artifacts import get_github_client
from src.main import app
from src.services.processor import SecurityProcessor

# Uses `client` fixture from conftest.py (handles init_db)


@pytest_asyncio.fixture
async def project(client):
    resp = await client.post("/projects", json={
        "name": f"Java App {uuid.uuid4().hex[:8]}",
        "github_url": f"https://github.com/test/{uuid.uuid4().hex}",
    })
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_project(client):
    resp = await client.post("/projects", json={
        "name": "Test Project",
        "github_url": f"https://github.com/test/{uuid.uuid4().hex}",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] is not None
    assert data["name"] == "Test Project"


@pytest.mark.asyncio
async def test_list_projects(client, project):
    resp = await client.get("/projects")
    assert resp.status_code == 200
    projects = resp.json()
    assert any(p["id"] == project["id"] for p in projects)


# ---------------------------------------------------------------------------
# POST /artifacts/process
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_artifact_returns_202(client, project):
    with patch.object(SecurityProcessor, "process_artifact", new_callable=AsyncMock, return_value=0):
        resp = await client.post("/artifacts/process", json={
            "github_artifact_id": 12345,
            "project_id": project["id"],
        })

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "pending"
    assert "db_artifact_id" in data


@pytest.mark.asyncio
async def test_process_artifact_404_for_unknown_project(client):
    resp = await client.post("/artifacts/process", json={
        "github_artifact_id": 12345,
        "project_id": 999999,
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_process_artifact_requires_api_key_when_configured(client, project):
    with patch("src.api.artifacts.settings") as mock_settings:
        mock_settings.CI_API_KEY = "secret-key"

        resp = await client.post("/artifacts/process", json={
            "github_artifact_id": 12345,
            "project_id": project["id"],
        })
        assert resp.status_code == 403

    with patch("src.api.artifacts.settings") as mock_settings, \
         patch.object(SecurityProcessor, "process_artifact", new_callable=AsyncMock, return_value=0):
        mock_settings.CI_API_KEY = "secret-key"
        resp2 = await client.post(
            "/artifacts/process",
            json={"github_artifact_id": 12345, "project_id": project["id"]},
            headers={"X-API-Key": "secret-key"},
        )
        assert resp2.status_code != 403


# ---------------------------------------------------------------------------
# GET /github/runs & /github/runs/{run_id}/artifacts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_github_runs(client):
    mock_gh = AsyncMock()
    mock_gh.list_workflow_runs.return_value = [
        {"id": 1001, "name": "CI Workflow", "conclusion": "success"},
    ]
    app.dependency_overrides[get_github_client] = lambda: mock_gh
    try:
        resp = await client.get("/github/runs")
    finally:
        app.dependency_overrides.pop(get_github_client, None)
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == 1001


@pytest.mark.asyncio
async def test_list_github_artifacts(client):
    mock_gh = AsyncMock()
    mock_gh.list_artifacts.return_value = [
        {"id": 555, "name": "sarif-results", "size_in_bytes": 1024},
    ]
    app.dependency_overrides[get_github_client] = lambda: mock_gh
    try:
        resp = await client.get("/github/runs/1001/artifacts")
    finally:
        app.dependency_overrides.pop(get_github_client, None)
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == 555


@pytest.mark.asyncio
async def test_list_github_runs_502_on_error(client):
    mock_gh = AsyncMock()
    mock_gh.list_workflow_runs.side_effect = Exception("network error")
    app.dependency_overrides[get_github_client] = lambda: mock_gh
    try:
        resp = await client.get("/github/runs")
    finally:
        app.dependency_overrides.pop(get_github_client, None)
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# POST /webhook/pipeline-complete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_webhook_pipeline_complete_accepted(client):
    # run-metadata.json format — extra fields ignored by pydantic
    metadata = {
        "run_id": 99001,
        "run_number": 42,
        "repository": "cochecheee/SAST_CICD",
        "ref": "refs/heads/main",
        "sha": "abc123",
        "pipeline_status": "success",
    }
    with patch("src.api.artifacts.settings") as mock_settings, \
         patch.object(SecurityProcessor, "process_run", new_callable=AsyncMock):
        mock_settings.CI_WEBHOOK_TOKEN = ""  # auth disabled
        mock_settings.GITHUB_OWNER = "cochecheee"
        mock_settings.GITHUB_REPO = "SAST_CICD"
        resp = await client.post("/webhook/pipeline-complete", json=metadata)
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "accepted"
    assert data["run_id"] == 99001


@pytest.mark.asyncio
async def test_webhook_pipeline_complete_requires_token_when_configured(client):
    metadata = {"run_id": 99002, "pipeline_status": "success"}

    with patch("src.api.artifacts.settings") as mock_settings:
        mock_settings.CI_WEBHOOK_TOKEN = "my-secret"
        mock_settings.GITHUB_OWNER = "cochecheee"
        mock_settings.GITHUB_REPO = "SAST_CICD"

        # Không có token → 403
        resp = await client.post("/webhook/pipeline-complete", json=metadata)
        assert resp.status_code == 403

        # Token sai → 403
        resp2 = await client.post(
            "/webhook/pipeline-complete",
            json=metadata,
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp2.status_code == 403

    with patch("src.api.artifacts.settings") as mock_settings, \
         patch.object(SecurityProcessor, "process_run", new_callable=AsyncMock):
        mock_settings.CI_WEBHOOK_TOKEN = "my-secret"
        mock_settings.GITHUB_OWNER = "cochecheee"
        mock_settings.GITHUB_REPO = "SAST_CICD"

        # Token đúng → 202
        resp3 = await client.post(
            "/webhook/pipeline-complete",
            json=metadata,
            headers={"Authorization": "Bearer my-secret"},
        )
        assert resp3.status_code == 202


# ---------------------------------------------------------------------------
# GET /findings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_findings_empty(client):
    resp = await client.get("/findings")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_findings_filter_by_project(client, project):
    resp = await client.get(f"/findings?project_id={project['id']}")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_list_findings_filter_by_severity(client):
    resp = await client.get("/findings?severity=high")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /findings/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_finding_404(client):
    resp = await client.get("/findings/999999")
    assert resp.status_code == 404

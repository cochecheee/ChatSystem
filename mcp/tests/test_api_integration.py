import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.api.artifacts import get_github_client
from src.main import app
from src.services.processor import SecurityProcessor

# Uses `client` and `project` fixtures from conftest.py


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
# V2.8 multi-tenant routing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_webhook_multi_tenant_routes_by_repository(client):
    """MULTI_TENANT_ENABLED=true + repository khớp existing project → dùng project đó."""
    # Seed project tương ứng repository payload
    create_resp = await client.post("/projects", json={
        "name": "Multi-tenant test",
        "github_url": "https://github.com/cochecheee/SAST_CICD",
    })
    assert create_resp.status_code == 201
    expected_id = create_resp.json()["id"]

    metadata = {
        "run_id": 99100,
        "repository": "cochecheee/SAST_CICD",
        "pipeline_status": "success",
    }
    with patch("src.api.artifacts.settings") as mock_settings, \
         patch.object(SecurityProcessor, "process_run", new_callable=AsyncMock):
        mock_settings.CI_WEBHOOK_TOKEN = ""
        mock_settings.MULTI_TENANT_ENABLED = True
        mock_settings.GITHUB_OWNER = "other"
        mock_settings.GITHUB_REPO = "fallback"
        resp = await client.post("/webhook/pipeline-complete", json=metadata)

    assert resp.status_code == 202
    data = resp.json()
    assert data["project_id"] == expected_id  # routed by payload.repository


@pytest.mark.asyncio
async def test_webhook_multi_tenant_falls_back_when_no_match(client):
    """MULTI_TENANT_ENABLED=true + repository không match → fallback settings."""
    metadata = {
        "run_id": 99101,
        "repository": "cochecheee/non-existent-repo",
        "pipeline_status": "success",
    }
    with patch("src.api.artifacts.settings") as mock_settings, \
         patch.object(SecurityProcessor, "process_run", new_callable=AsyncMock):
        mock_settings.CI_WEBHOOK_TOKEN = ""
        mock_settings.MULTI_TENANT_ENABLED = True
        mock_settings.GITHUB_OWNER = "fallback-owner"
        mock_settings.GITHUB_REPO = "fallback-repo"
        resp = await client.post("/webhook/pipeline-complete", json=metadata)

    assert resp.status_code == 202
    # Project created from fallback env values
    list_resp = await client.get("/projects")
    names = [p["name"] for p in list_resp.json()]
    assert "fallback-owner/fallback-repo" in names


@pytest.mark.asyncio
async def test_webhook_legacy_ignores_repository_when_flag_off(client):
    """MULTI_TENANT_ENABLED=false → ignore payload.repository, always env path."""
    # Seed project that WOULD match repository nếu flag on
    await client.post("/projects", json={
        "name": "Would-match",
        "github_url": "https://github.com/cochecheee/different",
    })

    metadata = {
        "run_id": 99102,
        "repository": "cochecheee/different",
        "pipeline_status": "success",
    }
    with patch("src.api.artifacts.settings") as mock_settings, \
         patch.object(SecurityProcessor, "process_run", new_callable=AsyncMock):
        mock_settings.CI_WEBHOOK_TOKEN = ""
        mock_settings.MULTI_TENANT_ENABLED = False
        mock_settings.GITHUB_OWNER = "legacy-owner"
        mock_settings.GITHUB_REPO = "legacy-repo"
        resp = await client.post("/webhook/pipeline-complete", json=metadata)

    assert resp.status_code == 202
    # Phải create project mới từ env, không dùng "Would-match"
    list_resp = await client.get("/projects")
    names = [p["name"] for p in list_resp.json()]
    assert "legacy-owner/legacy-repo" in names


# ---------------------------------------------------------------------------
# V2.8 P7 — POST /projects persist 9 field
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_project_persists_all_fields(client):
    payload = {
        "name": "Full Test",
        "github_url": f"https://github.com/test/{uuid.uuid4().hex}",
        "github_owner": "test",
        "github_repo": "demo-repo",
        "github_token": "ghp_xxxFAKE",
        "gemini_api_key": "AIzaSyFAKE",
        "gemini_model": "gemini-2.5-flash",
        "polling_workflow_name": "Security",
        "polling_branch": "main",
        "active": True,
    }
    resp = await client.post("/projects", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["github_owner"] == "test"
    assert data["github_repo"] == "demo-repo"
    # Secrets KHÔNG expose raw
    assert "github_token" not in data or data.get("github_token") in (None, "")
    assert data["has_github_token"] is True
    assert data["has_gemini_api_key"] is True
    assert data["polling_workflow_name"] == "Security"
    assert data["active"] is True


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

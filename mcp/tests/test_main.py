import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_root(client):
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert data["version"] == "0.2.0"


# ---------------------------------------------------------------------------
# Tests: GET /github/runs (PIPE-01, PIPE-03)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_github_runs_all_statuses(client):
    """PIPE-01/PIPE-03: /github/runs must NOT pass status=completed to GitHub.

    Patches GitHubClient.list_workflow_runs to assert it is called with
    status="" (empty string) so in_progress runs are included.
    """
    from unittest.mock import AsyncMock, patch

    mock_runs = [
        {"id": 1, "name": "CI", "status": "completed", "conclusion": "success",
         "head_branch": "main", "head_sha": "abc1234", "run_number": 1,
         "created_at": "2026-04-29T00:00:00Z", "html_url": "https://github.com"},
        {"id": 2, "name": "CI", "status": "in_progress", "conclusion": None,
         "head_branch": "main", "head_sha": "def5678", "run_number": 2,
         "created_at": "2026-04-29T01:00:00Z", "html_url": "https://github.com"},
    ]

    with patch(
        "src.api.artifacts.GitHubClient.list_workflow_runs",
        new_callable=AsyncMock,
        return_value=mock_runs,
    ) as mock_list:
        response = await client.get("/github/runs")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    statuses = {r["status"] for r in data}
    assert "in_progress" in statuses, "in_progress runs must be included (PIPE-03)"

    # Verify the backend did NOT pass status='completed'
    call_kwargs = mock_list.call_args.kwargs if mock_list.call_args.kwargs else {}
    call_args = mock_list.call_args.args if mock_list.call_args else ()
    # list_workflow_runs signature: (workflow_name, branch, status)
    # status must be "" (falsy) so github_client skips adding it to params
    passed_status = call_kwargs.get("status", call_args[2] if len(call_args) > 2 else "")
    assert passed_status == "", (
        f"Backend must call list_workflow_runs with status='' not '{passed_status}'"
    )

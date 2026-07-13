import io
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.github_client import GitHubClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_zip(files: dict[str, str]) -> bytes:
    """Build an in-memory ZIP containing the given filename→content mapping."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _mock_client(response_content: bytes | None = None, json_data: dict | None = None):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.content = response_content or b""
    mock_resp.json.return_value = json_data or {}

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.get = AsyncMock(return_value=mock_resp)
    return mock_http


# ---------------------------------------------------------------------------
# Tests: list_workflow_runs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_workflow_runs_filters_by_name():
    runs = [
        {"name": "CI Workflow", "id": 1},
        {"name": "Deploy", "id": 2},
    ]
    mock_http = _mock_client(json_data={"workflow_runs": runs})

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        result = await client.list_workflow_runs("CI Workflow", "main")

    assert len(result) == 1
    assert result[0]["id"] == 1


@pytest.mark.asyncio
async def test_list_workflow_runs_empty_name_returns_all():
    """Empty workflow_name = name-agnostic: no filtering, every run returned.

    This is the contract the poller's default (POLLING_WORKFLOW_NAME="") relies
    on — runs are kept regardless of name and the artifact profile does the
    real filtering downstream.
    """
    runs = [
        {"name": "CI Workflow", "id": 1},
        {"name": "Deploy", "id": 2},
        {"name": "anything", "id": 3},
    ]
    mock_http = _mock_client(json_data={"workflow_runs": runs})

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        result = await client.list_workflow_runs("", "main")

    assert [r["id"] for r in result] == [1, 2, 3]


@pytest.mark.asyncio
async def test_list_workflow_runs_empty():
    mock_http = _mock_client(json_data={"workflow_runs": []})
    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        result = await client.list_workflow_runs("CI Workflow", "main")
    assert result == []


# ---------------------------------------------------------------------------
# Tests: list_artifacts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_artifacts_returns_list():
    artifacts = [{"id": 101, "name": "sarif-results"}, {"id": 102, "name": "other"}]
    mock_http = _mock_client(json_data={"artifacts": artifacts})

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        result = await client.list_artifacts(run_id=999)

    assert len(result) == 2
    assert result[0]["id"] == 101


# ---------------------------------------------------------------------------
# Tests: list_run_jobs / get_job / fetch_job_logs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_run_jobs_returns_jobs_with_steps():
    jobs = [
        {
            "id": 7001,
            "name": "backend",
            "status": "in_progress",
            "conclusion": None,
            "steps": [{"name": "Checkout", "status": "completed", "conclusion": "success"}],
        },
    ]
    mock_http = _mock_client(json_data={"jobs": jobs})

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        result = await client.list_run_jobs(run_id=1001)

    assert result[0]["id"] == 7001
    assert result[0]["steps"][0]["conclusion"] == "success"
    # filter=latest keeps only the newest attempt — same view as the GitHub UI
    call_kwargs = mock_http.get.call_args.kwargs
    assert call_kwargs["params"].get("filter") == "latest"


@pytest.mark.asyncio
async def test_get_job_404_returns_none():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.get = AsyncMock(return_value=mock_resp)

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        assert await client.get_job(job_id=7001) is None


@pytest.mark.asyncio
async def test_fetch_job_logs_returns_text():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.content = b"2026-07-11T00:00:00Z ##[group]Run pytest\nline\n"
    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.get = AsyncMock(return_value=mock_resp)

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        result = await client.fetch_job_logs(job_id=7001)

    assert result is not None
    assert "##[group]Run pytest" in result


@pytest.mark.asyncio
async def test_fetch_job_logs_404_returns_none():
    """GitHub answers 404 while the job is still running — must map to None,
    not raise, so the API layer can return a descriptive 404."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.get = AsyncMock(return_value=mock_resp)

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        assert await client.fetch_job_logs(job_id=7001) is None


@pytest.mark.asyncio
async def test_fetch_job_logs_truncates_oversized_to_tail():
    from src.services.github_client import _MAX_LOG_BYTES

    head = b"OLD LINE\n" * 10
    tail_marker = b"FINAL ERROR LINE\n"
    filler = b"x" * _MAX_LOG_BYTES
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.content = head + filler + b"\n" + tail_marker
    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.get = AsyncMock(return_value=mock_resp)

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        result = await client.fetch_job_logs(job_id=7001)

    assert result is not None
    assert result.startswith("[... truncated")
    assert "FINAL ERROR LINE" in result
    assert "OLD LINE" not in result


# ---------------------------------------------------------------------------
# Tests: fetch_artifact / _extract_security_files
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_artifact_returns_sarif_content():
    sarif_content = '{"version":"2.1.0","runs":[]}'
    zip_bytes = _make_zip({"results/semgrep.sarif": sarif_content})
    mock_http = _mock_client(response_content=zip_bytes)

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        result = await client.fetch_artifact(artifact_id=101)

    assert len(result) == 1
    assert result[0]["filename"] == "results/semgrep.sarif"
    assert result[0]["content"] == sarif_content


@pytest.mark.asyncio
async def test_fetch_artifact_filters_non_security_files():
    zip_bytes = _make_zip({
        "results.sarif": "{}",
        "README.md": "# ignore me",
        "data.csv": "a,b,c",
    })
    mock_http = _mock_client(response_content=zip_bytes)

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        result = await client.fetch_artifact(artifact_id=101)

    filenames = [r["filename"] for r in result]
    assert "results.sarif" in filenames
    assert "README.md" not in filenames
    assert "data.csv" not in filenames


def test_extract_security_files_zip_slip_rejected():
    zip_bytes = _make_zip({"../evil.sarif": "malicious"})
    client = GitHubClient(token="tok", owner="owner", repo="repo")
    result = client._extract_security_files(zip_bytes)
    assert result == []


def test_extract_security_files_multiple_types():
    zip_bytes = _make_zip({
        "a.sarif": "sarif",
        "b.xml": "<xml/>",
        "c.json": "{}",
    })
    client = GitHubClient(token="tok", owner="owner", repo="repo")
    result = client._extract_security_files(zip_bytes)
    assert len(result) == 3


@pytest.mark.asyncio
async def test_fetch_artifact_raises_on_oversized_zip():
    from src.services.github_client import _MAX_ZIP_BYTES

    oversized = b"x" * (_MAX_ZIP_BYTES + 1)
    mock_http = _mock_client(response_content=oversized)

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        with pytest.raises(ValueError, match="too large"):
            await client.fetch_artifact(artifact_id=101)


# ---------------------------------------------------------------------------
# Tests: branch filter param (PIPE-02)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_branch_filter_param():
    """PIPE-02: list_workflow_runs must forward the branch param to GitHub API."""
    runs = [
        {"name": "CI", "id": 10, "head_branch": "feature/x"},
        {"name": "CI", "id": 11, "head_branch": "main"},
    ]
    mock_http = _mock_client(json_data={"workflow_runs": runs})

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        result = await client.list_workflow_runs(workflow_name="", branch="feature/x", status="")

    # Verify branch was passed as a query param to the GitHub API call
    mock_http.get.assert_called_once()
    call_kwargs = mock_http.get.call_args.kwargs
    assert "params" in call_kwargs, "branch must be passed via params dict"
    assert call_kwargs["params"].get("branch") == "feature/x"

    # Verify status was NOT added to params when empty
    assert "status" not in call_kwargs["params"], (
        "status must not appear in GitHub API params when empty string passed"
    )


@pytest.mark.asyncio
async def test_no_status_param_when_empty():
    """PIPE-01/PIPE-03: When status='' is passed, GitHub API params must not include status."""
    mock_http = _mock_client(json_data={"workflow_runs": []})

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        await client.list_workflow_runs(workflow_name="", branch="", status="")

    call_kwargs = mock_http.get.call_args.kwargs
    assert "status" not in call_kwargs.get("params", {}), (
        "Empty status must not be forwarded to GitHub API"
    )


# ---------------------------------------------------------------------------
# Tests: nested directory path extraction (DATA-02)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_nested_path_extraction():
    """Artifact ZIP with nested directory: all security files should be returned."""
    import json as _json
    sarif_content = _json.dumps({"version": "2.1.0", "runs": []})

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("results/codeql/java/codeql-results.sarif", sarif_content)
        zf.writestr("results/semgrep/semgrep-report.sarif", sarif_content)
    zip_bytes = buf.getvalue()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.content = zip_bytes

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.get = AsyncMock(return_value=mock_resp)

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        result = await client.fetch_artifact(artifact_id=101)

    filenames = [r["filename"] for r in result]
    assert "results/codeql/java/codeql-results.sarif" in filenames
    assert "results/semgrep/semgrep-report.sarif" in filenames


# ---------------------------------------------------------------------------
# Tests: fetch_file_content (DATA-03)
# ---------------------------------------------------------------------------

import base64 as _b64


@pytest.mark.asyncio
async def test_fetch_file_content_returns_decoded_text():
    encoded = _b64.b64encode(b"hello world\n").decode()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"encoding": "base64", "content": encoded}

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.get = AsyncMock(return_value=mock_resp)

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        result = await client.fetch_file_content("src/app.py")

    assert result == "hello world\n"


@pytest.mark.asyncio
async def test_fetch_file_content_404_returns_none():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {}

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.get = AsyncMock(return_value=mock_resp)

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        result = await client.fetch_file_content("missing.py")

    assert result is None


@pytest.mark.asyncio
async def test_fetch_file_content_binary_returns_none():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"encoding": "none"}

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.get = AsyncMock(return_value=mock_resp)

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        result = await client.fetch_file_content("logo.png")

    assert result is None


@pytest.mark.asyncio
async def test_fetch_file_content_path_traversal_blocked():
    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.get = AsyncMock()

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        result = await client.fetch_file_content("../etc/passwd")

    assert result is None
    mock_http.get.assert_not_called()

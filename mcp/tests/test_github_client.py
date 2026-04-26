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

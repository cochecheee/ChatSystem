import asyncio
import base64
import io
import logging
import zipfile
from pathlib import Path

import httpx

from ..core.config import settings

log = logging.getLogger(__name__)

_ALLOWED_EXTENSIONS = {".sarif", ".xml", ".json"}
_MAX_ZIP_BYTES = 50 * 1024 * 1024   # 50 MB
_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB per file
_MAX_LOG_BYTES = 2 * 1024 * 1024    # 2 MB per job log (tail kept on overflow)
_GITHUB_API = "https://api.github.com"
_ARTIFACT_RETRIES = 3               # download attempts before giving up
_RETRY_STATUS = {429, 500, 502, 503, 504}  # transient — worth retrying


class GitHubClient:
    def __init__(
        self,
        token: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> None:
        self._headers = {
            "Authorization": f"Bearer {token or settings.GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.owner = owner or settings.GITHUB_OWNER
        self.repo = repo or settings.GITHUB_REPO

    @classmethod
    def for_project(cls, project) -> "GitHubClient":
        """Build a client bound to a Project's stored credentials.

        Used by the poller (Day 2) so a single chat-system instance can
        scrape multiple repos without resetting global settings.
        """
        return cls(
            token=project.github_token or None,
            owner=project.github_owner or None,
            repo=project.github_repo or None,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def list_workflow_runs(
        self,
        workflow_name: str = "",
        branch: str = "",
        status: str = "completed",
    ) -> list[dict]:
        params: dict[str, str | int] = {"per_page": 30}
        if branch:
            params["branch"] = branch
        if status:
            params["status"] = status
        async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{self.owner}/{self.repo}/actions/runs",
                params=params,
            )
            resp.raise_for_status()
            runs = resp.json().get("workflow_runs", [])
        # Filter by workflow name only when explicitly specified
        if workflow_name:
            runs = [r for r in runs if r.get("name") == workflow_name]
        return runs

    async def get_workflow_run(self, run_id: int) -> dict | None:
        """Fetch metadata cho 1 run cụ thể. Trả None nếu 404."""
        async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{self.owner}/{self.repo}/actions/runs/{run_id}"
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    async def list_run_jobs(self, run_id: int) -> list[dict]:
        """List jobs (with per-step status/timing) for a workflow run.

        `filter=latest` returns only the most recent attempt — matches what
        the GitHub UI shows. Works while the run is still in progress, so
        the dashboard can render live step-by-step CI progress.
        """
        async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{self.owner}/{self.repo}/actions/runs/{run_id}/jobs",
                params={"per_page": 100, "filter": "latest"},
            )
            resp.raise_for_status()
            return resp.json().get("jobs", [])

    async def get_job(self, job_id: int) -> dict | None:
        """Fetch metadata cho 1 job cụ thể. Trả None nếu 404."""
        async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{self.owner}/{self.repo}/actions/jobs/{job_id}"
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    async def fetch_job_logs(self, job_id: int) -> str | None:
        """Download the plain-text log of a completed job.

        GitHub redirects to a short-lived blob-store URL, hence
        follow_redirects. Returns None on 404 — GitHub answers 404 both for
        unknown jobs and for jobs still running (logs only exist once the
        job finishes). Oversized logs keep only the tail, cut at a line
        boundary, so failure output (which sits at the end) survives.
        """
        async with httpx.AsyncClient(
            headers=self._headers, follow_redirects=True, timeout=60
        ) as client:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{self.owner}/{self.repo}/actions/jobs/{job_id}/logs"
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            raw = resp.content
        if len(raw) > _MAX_LOG_BYTES:
            tail = raw[-_MAX_LOG_BYTES:]
            newline = tail.find(b"\n")
            if newline != -1:
                tail = tail[newline + 1:]
            return (
                f"[... truncated — showing last {_MAX_LOG_BYTES // (1024 * 1024)} MB "
                f"of {len(raw) // (1024 * 1024)} MB ...]\n"
                + tail.decode("utf-8", errors="replace")
            )
        return raw.decode("utf-8", errors="replace")

    async def dispatch_workflow(self, workflow_filename: str, ref: str = "main") -> None:
        async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
            resp = await client.post(
                f"{_GITHUB_API}/repos/{self.owner}/{self.repo}/actions/workflows/{workflow_filename}/dispatches",
                json={"ref": ref},
            )
            resp.raise_for_status()

    async def rerun_workflow(self, run_id: int) -> None:
        async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
            resp = await client.post(
                f"{_GITHUB_API}/repos/{self.owner}/{self.repo}/actions/runs/{run_id}/rerun"
            )
            resp.raise_for_status()

    async def list_artifacts(self, run_id: int) -> list[dict]:
        async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{self.owner}/{self.repo}/actions/runs/{run_id}/artifacts"
            )
            resp.raise_for_status()
            return resp.json().get("artifacts", [])

    async def fetch_artifact(self, artifact_id: int) -> list[dict[str, str]]:
        """Download and extract a GitHub Actions artifact ZIP.

        Returns list of {"filename": str, "content": str} for security-relevant
        file types (.sarif, .xml, .json) only.

        Downloads are retried up to 3 times with exponential backoff (1s, 2s)
        on transient failures (network errors or 429/5xx). GitHub artifact
        downloads redirect to short-lived blob-store URLs that occasionally
        502/503 under load, so a bounded retry keeps ingest from dropping a
        whole run on a single flaky fetch. Non-transient errors (401/403/404)
        raise immediately — retrying them is pointless.
        """
        url = f"{_GITHUB_API}/repos/{self.owner}/{self.repo}/actions/artifacts/{artifact_id}/zip"
        zip_bytes: bytes | None = None
        for attempt in range(1, _ARTIFACT_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    headers=self._headers,
                    follow_redirects=True,
                    timeout=60,
                ) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                zip_bytes = resp.content
                break
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in _RETRY_STATUS or attempt == _ARTIFACT_RETRIES:
                    raise
                log.warning(
                    "fetch_artifact %s: HTTP %d (attempt %d/%d), retrying in %ds",
                    artifact_id, exc.response.status_code, attempt, _ARTIFACT_RETRIES, 2 ** (attempt - 1),
                )
            except httpx.TransportError as exc:
                if attempt == _ARTIFACT_RETRIES:
                    raise
                log.warning(
                    "fetch_artifact %s: %s (attempt %d/%d), retrying in %ds",
                    artifact_id, exc, attempt, _ARTIFACT_RETRIES, 2 ** (attempt - 1),
                )
            await asyncio.sleep(2 ** (attempt - 1))  # 1s, 2s

        assert zip_bytes is not None  # loop either set it or raised
        if len(zip_bytes) > _MAX_ZIP_BYTES:
            raise ValueError(
                f"Artifact ZIP too large: {len(zip_bytes)} bytes (limit {_MAX_ZIP_BYTES})"
            )

        return self._extract_security_files(zip_bytes)

    async def fetch_file_content(
        self,
        file_path: str,
        ref: str = "main",
    ) -> str | None:
        """Fetch decoded text content of a file at a given git ref.

        Returns None on 404, binary files (non-base64 encoding),
        files > 100 KB, and path traversal attempts.
        """
        # Guard: reject path traversal
        if not file_path or ".." in Path(file_path.lstrip("/")).parts:
            return None

        clean_path = file_path.lstrip("/")
        async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{self.owner}/{self.repo}/contents/{clean_path}",
                params={"ref": ref},
            )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            return None
        if data.get("encoding") != "base64" or "content" not in data:
            return None
        raw_bytes = base64.b64decode(data["content"])
        text = raw_bytes.decode("utf-8", errors="replace")
        return text[:100_000]  # cap at 100 KB to avoid bloating Gemini prompt

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_security_files(self, zip_bytes: bytes) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for info in zf.infolist():
                # Zip Slip: reject absolute paths and directory traversal
                if info.filename.startswith("/") or ".." in Path(info.filename).parts:
                    continue

                # Extension filter — only security-relevant files
                if Path(info.filename).suffix.lower() not in _ALLOWED_EXTENSIONS:
                    continue

                # Zip Bomb: skip oversized entries
                if info.file_size > _MAX_FILE_BYTES:
                    continue

                with zf.open(info) as f:
                    content = f.read(_MAX_FILE_BYTES).decode("utf-8", errors="replace")

                results.append({"filename": info.filename, "content": content})

        return results

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..core.config import settings
from ..core.db import AsyncSessionLocal
from ..models.entities import Project
from ..repositories import ProjectRepository
from .github_client import GitHubClient
from .processor import SecurityProcessor

log = logging.getLogger(__name__)

# Which GitHub run conclusions are worth ingesting. We deliberately include
# "failure": in a security pipeline a failed run is usually the security gate
# tripping (findings exceeded threshold) — exactly the runs whose artifacts we
# most need to show. A SAST job can also succeed and upload its report even
# when an unrelated job (e.g. DAST) fails the overall run. "cancelled" /
# "skipped" / "timed_out" / None are excluded — no reliable artifacts.
INGESTIBLE_CONCLUSIONS = ("success", "failure")


class GitHubPoller:
    """Background task — poll GitHub cho workflow runs mới.

    Hai mode dựa trên settings.MULTI_TENANT_ENABLED:
      - False (legacy): poll 1 repo configured qua settings.GITHUB_OWNER/REPO.
        Tự create Project nếu chưa có, dùng env credentials.
      - True (V2.8 B3): mỗi cycle query `ProjectRepository.list_active()` →
        poll song song cho từng project (asyncio.gather + semaphore cap).
        Per-project GitHubClient với credentials từ row.
    """

    def __init__(
        self,
        processor: SecurityProcessor | None = None,
        github_client: GitHubClient | None = None,
        session_factory: async_sessionmaker | None = None,
        max_concurrent: int = 3,
    ) -> None:
        self.processor = processor or SecurityProcessor()
        self.github_client = github_client or GitHubClient()
        self.session_factory = session_factory or AsyncSessionLocal
        self.interval = settings.POLLING_INTERVAL_SECONDS
        self.workflow_name = settings.POLLING_WORKFLOW_NAME
        self.branch = settings.POLLING_BRANCH
        self._github_url = (
            f"https://github.com/{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}"
        )
        self._semaphore = asyncio.Semaphore(max_concurrent)

    # ------------------------------------------------------------------

    async def start(self) -> None:
        log.info(
            "Poller started — interval=%ds workflow=%r branch=%r multi_tenant=%s",
            self.interval,
            self.workflow_name,
            self.branch,
            settings.MULTI_TENANT_ENABLED,
        )
        while True:
            await asyncio.sleep(self.interval)
            try:
                await self._poll()
            except Exception as exc:
                log.error("Polling error: %s", exc)

    # ------------------------------------------------------------------

    async def _poll(self) -> None:
        """Route mode theo MULTI_TENANT_ENABLED."""
        if settings.MULTI_TENANT_ENABLED:
            await self._poll_multi_tenant()
        else:
            await self._poll_single_tenant()

    async def _poll_multi_tenant(self) -> None:
        """V2.8 B3 — iterate ProjectRepository.list_active() in parallel.

        Mỗi project chạy trong coroutine riêng, asyncio.Semaphore cap
        concurrency để không hit GitHub rate limit 5000/h per PAT.
        1 project lỗi không crash cycle (return_exceptions=True).
        """
        async with self.session_factory() as session:
            projects = await ProjectRepository(session).list_active()

        if not projects:
            log.debug("No active projects to poll")
            return

        log.info("Multi-tenant poll: %d active project(s)", len(projects))
        await asyncio.gather(
            *(self._poll_one_project(p) for p in projects),
            return_exceptions=True,
        )

    async def _poll_one_project(self, project) -> None:
        """Single project polling — guarded by semaphore."""
        async with self._semaphore:
            try:
                gh = GitHubClient.for_project(project)
                runs = await gh.list_workflow_runs(
                    project.polling_workflow_name or self.workflow_name,
                    project.polling_branch or self.branch,
                )
                last_run_id = project.last_processed_run_id or 0
                new_runs = sorted(
                    [
                        r for r in runs
                        if r["id"] > last_run_id
                        and r.get("conclusion") in INGESTIBLE_CONCLUSIONS
                    ],
                    key=lambda r: r["id"],
                )
                if not new_runs:
                    log.debug(
                        "Project %d (%s): no new runs since %d",
                        project.id, project.github_repo, last_run_id,
                    )
                    return

                log.info(
                    "Project %d (%s/%s): %d new run(s)",
                    project.id, project.github_owner, project.github_repo,
                    len(new_runs),
                )
                for run in new_runs:
                    try:
                        await self.processor.process_run(project.id, run["id"])
                        # Update last_processed_run_id transactionally
                        async with self.session_factory() as session:
                            db_proj = await session.get(Project, project.id)
                            if db_proj is not None:
                                db_proj.last_processed_run_id = run["id"]
                                await session.commit()
                    except Exception as exc:
                        log.error(
                            "Project %d run %d failed: %s",
                            project.id, run["id"], exc,
                        )
            except Exception:
                log.exception("Poll project %d failed", project.id)

    async def _poll_single_tenant(self) -> None:
        """Legacy single-tenant flow — 1 project from env settings."""
        async with self.session_factory() as session:
            project = await self._get_or_create_project(session)
            last_run_id = project.last_processed_run_id or 0

            runs = await self.github_client.list_workflow_runs(
                self.workflow_name, self.branch
            )
            new_runs = [
                r
                for r in runs
                if r["id"] > last_run_id
                and r.get("conclusion") in INGESTIBLE_CONCLUSIONS
            ]

            if not new_runs:
                log.debug("No new workflow runs since run_id=%d", last_run_id)
                return

            for run in sorted(new_runs, key=lambda r: r["id"]):
                log.info("Processing workflow run %d", run["id"])
                try:
                    await self.processor.process_run(project.id, run["id"])
                    project.last_processed_run_id = run["id"]
                    await session.commit()
                except Exception as exc:
                    log.error("Failed to process run %d: %s", run["id"], exc)

    # ------------------------------------------------------------------

    async def _get_or_create_project(self, session) -> Project:
        result = await session.execute(
            select(Project).where(Project.github_url == self._github_url)
        )
        project = result.scalar_one_or_none()
        if project is None:
            project = Project(
                name=f"{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}",
                github_url=self._github_url,
                github_owner=settings.GITHUB_OWNER,
                github_repo=settings.GITHUB_REPO,
                github_token=settings.GITHUB_TOKEN,
                gemini_api_key=settings.GEMINI_API_KEY,
                gemini_model=settings.GEMINI_MODEL,
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)
            log.info("Created project for %s", self._github_url)
        return project

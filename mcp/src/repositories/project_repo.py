"""Project repository."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.entities import Project


class ProjectRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, project_id: int) -> Project | None:
        return await self.session.get(Project, project_id)

    async def get_by_github_url(self, github_url: str) -> Project | None:
        result = await self.session.execute(
            select(Project).where(Project.github_url == github_url)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Project]:
        result = await self.session.execute(select(Project))
        return list(result.scalars().all())

    async def create(self, **fields) -> Project:
        """Create a project. `name` and `github_url` are required; the rest
        (github_owner/repo/token, gemini_*, polling_*, artifact_profile,
        active) fall back to entity defaults when omitted."""
        project = Project(**fields)
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def get_or_create_by_github_url(
        self, *, name: str, github_url: str, **extra,
    ) -> Project:
        existing = await self.get_by_github_url(github_url)
        if existing is not None:
            return existing
        return await self.create(name=name, github_url=github_url, **extra)

    async def update(self, project: Project, fields: dict) -> Project:
        """Apply non-None fields to project, commit, return refreshed."""
        for k, v in fields.items():
            if v is not None and hasattr(project, k):
                setattr(project, k, v)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def list_active(self) -> list[Project]:
        """Active projects with credentials wired — what the poller iterates."""
        result = await self.session.execute(
            select(Project).where(
                Project.active == 1,
                Project.github_token != "",
                Project.github_owner != "",
                Project.github_repo != "",
            )
        )
        return list(result.scalars().all())

    async def delete(self, project: Project) -> None:
        await self.session.delete(project)
        await self.session.commit()

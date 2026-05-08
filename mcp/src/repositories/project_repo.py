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

    async def create(self, *, name: str, github_url: str) -> Project:
        project = Project(name=name, github_url=github_url)
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def get_or_create_by_github_url(
        self, *, name: str, github_url: str
    ) -> Project:
        existing = await self.get_by_github_url(github_url)
        if existing is not None:
            return existing
        return await self.create(name=name, github_url=github_url)

    async def delete(self, project: Project) -> None:
        await self.session.delete(project)
        await self.session.commit()

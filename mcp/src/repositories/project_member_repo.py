"""Repository for V3.0 per-project RBAC."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.entities import ProjectMember


# Role lattice — higher index = more permission.
ROLE_LATTICE = ["viewer", "developer", "security_lead", "owner"]


def role_satisfies(actual: str, required: str) -> bool:
    """True if `actual` role is >= `required` in the V3.0 lattice."""
    try:
        return ROLE_LATTICE.index(actual) >= ROLE_LATTICE.index(required)
    except ValueError:
        return False


class ProjectMemberRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_role(self, project_id: int, username: str) -> str | None:
        """Return the role for (project, user) or None when not a member."""
        result = await self.session.execute(
            select(ProjectMember.role).where(
                ProjectMember.project_id == project_id,
                ProjectMember.username == username,
            )
        )
        row = result.first()
        return row[0] if row else None

    async def list_for_project(self, project_id: int) -> list[ProjectMember]:
        result = await self.session.execute(
            select(ProjectMember).where(ProjectMember.project_id == project_id)
        )
        return list(result.scalars().all())

    async def list_for_user(self, username: str) -> list[ProjectMember]:
        result = await self.session.execute(
            select(ProjectMember).where(ProjectMember.username == username)
        )
        return list(result.scalars().all())

    async def memberships_dict(self, username: str) -> dict[int, str]:
        """{ project_id: role } — convenience for JWT encoding."""
        rows = await self.list_for_user(username)
        return {m.project_id: m.role for m in rows}

    async def upsert(self, *, project_id: int, username: str, role: str) -> ProjectMember:
        existing = await self.session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.username == username,
            )
        )
        member = existing.scalar_one_or_none()
        if member is None:
            member = ProjectMember(project_id=project_id, username=username, role=role)
            self.session.add(member)
        else:
            member.role = role
        await self.session.commit()
        await self.session.refresh(member)
        return member

    async def remove(self, *, project_id: int, username: str) -> bool:
        result = await self.session.execute(
            delete(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.username == username,
            )
        )
        await self.session.commit()
        return (result.rowcount or 0) > 0

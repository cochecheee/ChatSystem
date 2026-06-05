"""Artifact repository."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.entities import Artifact


class ArtifactRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, artifact_id: int) -> Artifact | None:
        return await self.session.get(Artifact, artifact_id)

    async def list_for_run(self, run_id: int) -> list[Artifact]:
        result = await self.session.execute(
            select(Artifact).where(Artifact.github_run_id == run_id)
        )
        return list(result.scalars().all())

    async def list_for_project(self, project_id: int) -> list[Artifact]:
        result = await self.session.execute(
            select(Artifact).where(Artifact.project_id == project_id)
        )
        return list(result.scalars().all())

    async def latest_run_id_with_findings(
        self, *, project_id: int | None = None, project_ids: list[int] | None = None,
    ) -> int | None:
        """Run ID mới nhất có findings (theo Artifact.created_at).

        Một run có thể có nhiều artifacts; trả về run_id của artifact mới nhất
        mà có ít nhất 1 finding trong DB. Dùng cho Overview "scan mới nhất".

        V3.7: `project_ids` giới hạn trong tập project của member (khi non-admin
        chọn "All projects"). project_id (đơn) vẫn ưu tiên nếu được truyền.
        """
        from sqlalchemy import desc, false as sql_false
        from sqlalchemy import func as sql_func

        from ..models.entities import Finding
        query = (
            select(Artifact.github_run_id, sql_func.max(Artifact.created_at).label("latest"))
            .join(Finding, Finding.artifact_id == Artifact.id)
            .where(Artifact.github_run_id.is_not(None))
        )
        if project_id is not None:
            query = query.where(Artifact.project_id == project_id)
        elif project_ids is not None:
            query = query.where(
                Artifact.project_id.in_(project_ids) if project_ids else sql_false()
            )
        query = (
            query.group_by(Artifact.github_run_id)
            .order_by(desc("latest"))
            .limit(1)
        )
        result = await self.session.execute(query)
        row = result.first()
        return row[0] if row else None

    async def create(
        self,
        *,
        github_artifact_id: str,
        project_id: int,
        status: str = "pending",
    ) -> Artifact:
        artifact = Artifact(
            github_artifact_id=github_artifact_id,
            project_id=project_id,
            status=status,
        )
        self.session.add(artifact)
        await self.session.commit()
        await self.session.refresh(artifact)
        return artifact

    async def delete_by_ids(self, artifact_ids: list[int]) -> None:
        if not artifact_ids:
            return
        await self.session.execute(delete(Artifact).where(Artifact.id.in_(artifact_ids)))

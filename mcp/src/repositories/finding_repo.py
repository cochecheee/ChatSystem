"""Finding repository — tất cả DB query liên quan tới Finding."""
from __future__ import annotations

from sqlalchemy import delete, func as sql_func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.entities import Artifact, Finding


# Tools được coi là dependency-scan thay vì SAST. Dùng cho filter ?category=
DEPS_TOOLS: set[str] = {
    "dependency-check",
    "owasp-dependency-check",
    "trivy",
    "trivy-deps",
}

# Runtime/DAST tools (V2.3). Findings tới từ scan app đang chạy.
DAST_TOOLS: set[str] = {
    "owasp-zap",
    "zap",
    "zaproxy",
}


class FindingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, finding_id: int) -> Finding | None:
        return await self.session.get(Finding, finding_id)

    async def list_with_filters(
        self,
        *,
        project_id: int | None = None,
        severity: str | None = None,
        tool: str | None = None,
        status: str | None = None,
        category: str | None = None,
        q: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Finding]:
        """List findings với filter mở rộng + pagination."""
        query = select(Finding).join(Artifact)
        if project_id is not None:
            query = query.where(Artifact.project_id == project_id)
        if severity is not None:
            query = query.where(Finding.severity == severity)
        if tool is not None:
            query = query.where(Finding.tool == tool)
        if status is not None:
            query = query.where(Finding.status == status)
        if category is not None:
            cat = category.lower()
            if cat == "deps":
                query = query.where(Finding.tool.in_(DEPS_TOOLS))
            elif cat == "dast":
                query = query.where(Finding.tool.in_(DAST_TOOLS))
            elif cat == "sast":
                # SAST = code scan, exclude both deps + dast runtime tools.
                query = query.where(
                    ~Finding.tool.in_(DEPS_TOOLS | DAST_TOOLS)
                )
        if q:
            like = f"%{q.lower()}%"
            query = query.where(
                or_(
                    sql_func.lower(Finding.message).like(like),
                    sql_func.lower(Finding.file_path).like(like),
                    sql_func.lower(Finding.rule_id).like(like),
                )
            )
        query = query.order_by(Finding.id.desc()).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_for_run(self, run_id: int) -> list[Finding]:
        """Tất cả findings từ artifacts của 1 GitHub run, sorted by severity + rule."""
        artifact_result = await self.session.execute(
            select(Artifact).where(Artifact.github_run_id == run_id)
        )
        artifacts = artifact_result.scalars().all()
        if not artifacts:
            return []
        artifact_ids = [a.id for a in artifacts]
        finding_result = await self.session.execute(
            select(Finding)
            .where(Finding.artifact_id.in_(artifact_ids))
            .order_by(Finding.severity, Finding.rule_id)
        )
        return list(finding_result.scalars().all())

    async def list_recent_critical(self, limit: int = 5) -> list[Finding]:
        """Recent critical/high findings — dùng cho chat context."""
        result = await self.session.execute(
            select(Finding)
            .where(Finding.severity.in_(["critical", "high"]))
            .order_by(Finding.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_for_report(
        self,
        *,
        project_id: int | None = None,
        severity: str | None = None,
    ) -> list[Finding]:
        """Findings cho HTML report — không pagination."""
        query = select(Finding)
        if project_id is not None:
            query = query.join(Artifact).where(Artifact.project_id == project_id)
        if severity is not None:
            query = query.where(Finding.severity == severity)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def delete_by_artifact_ids(self, artifact_ids: list[int]) -> None:
        if not artifact_ids:
            return
        await self.session.execute(delete(Finding).where(Finding.artifact_id.in_(artifact_ids)))

    async def count_with_filters(
        self,
        *,
        project_id: int | None = None,
        severity: str | None = None,
        tool: str | None = None,
        status: str | None = None,
        category: str | None = None,
        q: str | None = None,
    ) -> int:
        """Count rows match filter — dùng cho pagination total + stats."""
        query = select(sql_func.count(Finding.id)).select_from(Finding).join(Artifact)
        if project_id is not None:
            query = query.where(Artifact.project_id == project_id)
        if severity is not None:
            query = query.where(Finding.severity == severity)
        if tool is not None:
            query = query.where(Finding.tool == tool)
        if status is not None:
            query = query.where(Finding.status == status)
        if category is not None:
            cat = category.lower()
            if cat == "deps":
                query = query.where(Finding.tool.in_(DEPS_TOOLS))
            elif cat == "dast":
                query = query.where(Finding.tool.in_(DAST_TOOLS))
            elif cat == "sast":
                query = query.where(
                    ~Finding.tool.in_(DEPS_TOOLS | DAST_TOOLS)
                )
        if q:
            like = f"%{q.lower()}%"
            query = query.where(
                or_(
                    sql_func.lower(Finding.message).like(like),
                    sql_func.lower(Finding.file_path).like(like),
                    sql_func.lower(Finding.rule_id).like(like),
                )
            )
        result = await self.session.execute(query)
        return int(result.scalar_one() or 0)

    async def count_by_severity(self) -> dict[str, int]:
        result = await self.session.execute(
            select(Finding.severity, sql_func.count(Finding.id)).group_by(Finding.severity)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    async def count_by_status(self) -> dict[str, int]:
        result = await self.session.execute(
            select(Finding.status, sql_func.count(Finding.id)).group_by(Finding.status)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    async def count_by_tool(self) -> dict[str, int]:
        result = await self.session.execute(
            select(Finding.tool, sql_func.count(Finding.id)).group_by(Finding.tool)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    async def count_ai_analyzed(self) -> int:
        result = await self.session.execute(
            select(sql_func.count(Finding.id)).where(Finding.ai_analysis.is_not(None))
        )
        return int(result.scalar_one() or 0)

    async def count_total(self) -> int:
        result = await self.session.execute(select(sql_func.count(Finding.id)))
        return int(result.scalar_one() or 0)

"""Finding repository — tất cả DB query liên quan tới Finding."""
from __future__ import annotations

from sqlalchemy import delete, false as sql_false, or_, select
from sqlalchemy import func as sql_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
        # Eager-load Artifact so callers can read project_id without async re-fetch.
        result = await self.session.execute(
            select(Finding)
            .options(selectinload(Finding.artifact))
            .where(Finding.id == finding_id)
        )
        return result.scalar_one_or_none()

    async def list_with_filters(
        self,
        *,
        project_id: int | None = None,
        project_ids: list[int] | None = None,
        severity: str | None = None,
        tool: str | None = None,
        status: str | None = None,
        category: str | None = None,
        q: str | None = None,
        run_id: int | None = None,
        exclude_revoked: bool = False,
        latest_run_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Finding]:
        """List findings với filter mở rộng + pagination.

        project_ids (V3.3): khi non-None, restrict to that set — used by the
        RBAC layer to enforce membership-scoped reads. Empty list → empty
        result (user authed but no memberships).

        latest_run_only (V3.8): chỉ findings của run mới nhất mỗi project —
        current-state, tránh nhân bản qua các lần CI chạy lại.
        """
        # V3.2 SMELL-6: eager-load Artifact so FindingOut.project_id resolves
        # without triggering an async lazy load during serialization.
        query = select(Finding).join(Artifact).options(selectinload(Finding.artifact))
        if project_id is not None:
            query = query.where(Artifact.project_id == project_id)
        if project_ids is not None:
            if not project_ids:
                return []
            query = query.where(Artifact.project_id.in_(project_ids))
        if latest_run_only:
            query = query.where(
                Artifact.github_run_id.in_(self._latest_run_ids(project_id, project_ids))
            )
        if run_id is not None:
            query = query.where(Artifact.github_run_id == run_id)
        if severity is not None:
            query = query.where(Finding.severity == severity)
        if tool is not None:
            query = query.where(Finding.tool == tool)
        if status is not None:
            query = query.where(Finding.status == status)
        if exclude_revoked:
            query = query.where(Finding.status != "REVOKED")
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

    async def list_for_run(
        self, run_id: int, *, exclude_revoked: bool = False,
    ) -> list[Finding]:
        """Tất cả findings từ artifacts của 1 GitHub run, sorted by severity + rule.

        `exclude_revoked=True` bỏ finding REVOKED — dùng cho các view "latest
        scan" để FP đã triage không hiện lại sau mỗi lần re-scan. Callers cần
        full breakdown theo status (vd stats_service.latest_scan) để mặc định
        False rồi tự nhóm.
        """
        artifact_result = await self.session.execute(
            select(Artifact).where(Artifact.github_run_id == run_id)
        )
        artifacts = artifact_result.scalars().all()
        if not artifacts:
            return []
        artifact_ids = [a.id for a in artifacts]
        query = (
            select(Finding)
            .where(Finding.artifact_id.in_(artifact_ids))
            .order_by(Finding.severity, Finding.rule_id)
        )
        if exclude_revoked:
            query = query.where(Finding.status != "REVOKED")
        finding_result = await self.session.execute(query)
        return list(finding_result.scalars().all())

    async def list_recent_critical(self, limit: int = 5) -> list[Finding]:
        """Recent critical/high findings — dùng cho chat context.

        Bỏ REVOKED: AI không nên trích dẫn finding đã bị triage là false-positive.
        """
        result = await self.session.execute(
            select(Finding)
            .where(Finding.severity.in_(["critical", "high"]))
            .where(Finding.status != "REVOKED")
            .order_by(Finding.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_for_report(
        self,
        *,
        project_id: int | None = None,
        severity: str | None = None,
        latest_run_only: bool = False,
    ) -> list[Finding]:
        """Findings cho HTML report — không pagination.

        Eager-load Artifact để report đọc được github_run_id / project_id
        mà không trigger lazy-load (async) khi render.

        latest_run_only (V3.8): report phản ánh current-state = run mới nhất
        mỗi project (khớp dashboard; không cộng dồn các lần CI chạy lại).
        """
        query = select(Finding).options(selectinload(Finding.artifact))
        joined = False
        if project_id is not None:
            query = query.join(Artifact).where(Artifact.project_id == project_id)
            joined = True
        if severity is not None:
            query = query.where(Finding.severity == severity)
        if latest_run_only:
            if not joined:
                query = query.join(Artifact)
            query = query.where(
                Artifact.github_run_id.in_(self._latest_run_ids(project_id, None))
            )
        query = query.order_by(Finding.id.desc())
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
        project_ids: list[int] | None = None,
        severity: str | None = None,
        tool: str | None = None,
        status: str | None = None,
        category: str | None = None,
        q: str | None = None,
        run_id: int | None = None,
        exclude_revoked: bool = False,
        exclude_approved: bool = False,
        latest_run_only: bool = False,
    ) -> int:
        """Count rows match filter — dùng cho pagination total + stats.

        exclude_approved (§4.2.3): loại finding APPROVED khỏi count. Dùng cho
        Security Gate — /approve là "chấp nhận rủi ro có kiểm toán" nên finding
        đã APPROVED không còn chặn PR merge (giống REVOKED = false-positive).
        """
        query = select(sql_func.count(Finding.id)).select_from(Finding).join(Artifact)
        if project_id is not None:
            query = query.where(Artifact.project_id == project_id)
        if project_ids is not None:
            if not project_ids:
                return 0
            query = query.where(Artifact.project_id.in_(project_ids))
        if latest_run_only:
            query = query.where(
                Artifact.github_run_id.in_(self._latest_run_ids(project_id, project_ids))
            )
        if run_id is not None:
            query = query.where(Artifact.github_run_id == run_id)
        if severity is not None:
            query = query.where(Finding.severity == severity)
        if tool is not None:
            query = query.where(Finding.tool == tool)
        if status is not None:
            query = query.where(Finding.status == status)
        if exclude_revoked:
            query = query.where(Finding.status != "REVOKED")
        if exclude_approved:
            query = query.where(Finding.status != "APPROVED")
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

    @staticmethod
    def _latest_run_ids(project_id: int | None, project_ids: list[int] | None):
        """Subquery → github_run_id của run MỚI NHẤT (theo Artifact.created_at,
        trong số run CÓ findings) cho TỪNG project trong scope.

        Cốt lõi của nguyên tắc "dashboard = current state = lần quét gần nhất":
        mỗi lần CI chạy lại tạo bộ Finding mới, nên current-state chỉ lấy run
        mới nhất từng project (tránh cộng dồn/nhân bản qua các run cũ).

        Portable (không dùng window function — chạy cả MariaDB 10.4 + Postgres):
        gom max(created_at) theo (project, run) → lấy run có created_at lớn nhất
        mỗi project. github_run_id là duy nhất theo repo nên IN không lẫn project.
        """
        run_times = (
            select(
                Artifact.project_id.label("pid"),
                Artifact.github_run_id.label("rid"),
                sql_func.max(Artifact.created_at).label("t"),
            )
            .join(Finding, Finding.artifact_id == Artifact.id)
            .where(Artifact.github_run_id.is_not(None))
        )
        if project_id is not None:
            run_times = run_times.where(Artifact.project_id == project_id)
        elif project_ids is not None:
            run_times = run_times.where(
                Artifact.project_id.in_(project_ids) if project_ids else sql_false()
            )
        run_times = run_times.group_by(
            Artifact.project_id, Artifact.github_run_id,
        ).subquery()
        proj_latest = (
            select(run_times.c.pid, sql_func.max(run_times.c.t).label("tmax"))
            .group_by(run_times.c.pid)
            .subquery()
        )
        return (
            select(run_times.c.rid).join(
                proj_latest,
                (run_times.c.pid == proj_latest.c.pid)
                & (run_times.c.t == proj_latest.c.tmax),
            )
        )

    @staticmethod
    def _scope(
        query, project_id: int | None, project_ids: list[int] | None,
        latest_run_only: bool = False,
    ):
        """Apply project scoping. project_id wins; project_ids restricts to a
        set (V3.7 — used to scope global stats to a member's projects). Empty
        project_ids → match nothing (authenticated user with zero memberships).

        latest_run_only (V3.8): chỉ tính findings của run mới nhất mỗi project
        → current-state nhất quán với Overview latest-scan.
        """
        joined = False
        if project_id is not None:
            query = query.join(Artifact).where(Artifact.project_id == project_id)
            joined = True
        elif project_ids is not None:
            if not project_ids:
                return query.join(Artifact).where(sql_false())
            query = query.join(Artifact).where(Artifact.project_id.in_(project_ids))
            joined = True
        if latest_run_only:
            if not joined:
                query = query.join(Artifact)
            query = query.where(
                Artifact.github_run_id.in_(
                    FindingRepository._latest_run_ids(project_id, project_ids)
                )
            )
        return query

    async def count_by_severity(
        self, *, project_id: int | None = None, project_ids: list[int] | None = None,
        exclude_revoked: bool = False, latest_run_only: bool = False,
    ) -> dict[str, int]:
        query = self._scope(
            select(Finding.severity, sql_func.count(Finding.id)),
            project_id, project_ids, latest_run_only,
        )
        if exclude_revoked:
            query = query.where(Finding.status != "REVOKED")
        query = query.group_by(Finding.severity)
        result = await self.session.execute(query)
        return {row[0]: int(row[1]) for row in result.all()}

    async def count_by_status(
        self, *, project_id: int | None = None, project_ids: list[int] | None = None,
        latest_run_only: bool = False,
    ) -> dict[str, int]:
        query = self._scope(
            select(Finding.status, sql_func.count(Finding.id)),
            project_id, project_ids, latest_run_only,
        ).group_by(Finding.status)
        result = await self.session.execute(query)
        return {row[0]: int(row[1]) for row in result.all()}

    async def count_by_tool(
        self, *, project_id: int | None = None, project_ids: list[int] | None = None,
        latest_run_only: bool = False,
    ) -> dict[str, int]:
        query = self._scope(
            select(Finding.tool, sql_func.count(Finding.id)),
            project_id, project_ids, latest_run_only,
        ).group_by(Finding.tool)
        result = await self.session.execute(query)
        return {row[0]: int(row[1]) for row in result.all()}

    async def count_ai_analyzed(
        self, *, project_id: int | None = None, project_ids: list[int] | None = None,
        latest_run_only: bool = False,
    ) -> int:
        query = self._scope(
            select(sql_func.count(Finding.id)).where(Finding.ai_analysis.is_not(None)),
            project_id, project_ids, latest_run_only,
        )
        result = await self.session.execute(query)
        return int(result.scalar_one() or 0)

    async def find_revoked_hashes(
        self, hashes: set[str], *, project_id: int | None = None,
    ) -> dict[str, dict]:
        """Return {dedup_hash: {revoked_by, justification, revoked_at}} for any
        prior Finding rows with that hash currently marked REVOKED. Used by the
        V3.1 cross-run learning loop to auto-suppress findings that a human
        already dismissed in a previous run.

        Scoped by project when given — same hash on two repos is still two
        independent decisions.
        """
        if not hashes:
            return {}
        query = select(
            Finding.dedup_hash,
            Finding.revoked_by,
            Finding.revoke_justification,
            Finding.revoked_at,
        ).where(
            Finding.status == "REVOKED",
            Finding.dedup_hash.in_(hashes),
        )
        if project_id is not None:
            query = query.join(Artifact).where(Artifact.project_id == project_id)
        result = await self.session.execute(query)
        out: dict[str, dict] = {}
        for h, by, just, at in result.all():
            # First revoke wins (oldest decision is the canonical one)
            if h not in out:
                out[h] = {
                    "revoked_by": by,
                    "revoke_justification": just,
                    "revoked_at": at,
                }
        return out

    async def find_approved_hashes(
        self, hashes: set[str], *, project_id: int | None = None,
    ) -> dict[str, dict]:
        """Return {dedup_hash: {approved_by, justification, approved_at}} for
        prior Finding rows currently APPROVED. Mirror of find_revoked_hashes:
        an /approve (accepted-risk) must also carry forward across runs so the
        gate does NOT re-flag the same finding on the next scan — matching
        revoke's Tier-1 behaviour. Scoped by project."""
        if not hashes:
            return {}
        query = select(
            Finding.dedup_hash,
            Finding.approved_by,
            Finding.justification,
            Finding.approved_at,
        ).where(
            Finding.status == "APPROVED",
            Finding.dedup_hash.in_(hashes),
        )
        if project_id is not None:
            query = query.join(Artifact).where(Artifact.project_id == project_id)
        result = await self.session.execute(query)
        out: dict[str, dict] = {}
        for h, by, just, at in result.all():
            if h not in out:  # first approval wins (canonical decision)
                out[h] = {"approved_by": by, "justification": just, "approved_at": at}
        return out

    async def count_total(
        self, *, project_id: int | None = None, project_ids: list[int] | None = None,
        latest_run_only: bool = False,
    ) -> int:
        query = self._scope(
            select(sql_func.count(Finding.id)), project_id, project_ids, latest_run_only,
        )
        result = await self.session.execute(query)
        return int(result.scalar_one() or 0)

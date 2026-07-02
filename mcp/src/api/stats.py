"""Stats endpoints — pre-aggregated counts cho dashboard KPI/trend."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import User, allowed_project_ids, ensure_project_in_scope, require_read_access
from ..core.db import get_session
from ..services.stats_service import StatsService

router = APIRouter(
    prefix="/stats", tags=["stats"],
    # V3.3 — every stats endpoint goes through the read kill-switch.
)


@router.get("/overview", summary="Aggregated KPI cho Overview page")
async def stats_overview(
    project_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_read_access),
) -> dict[str, Any]:
    """Counts theo severity/status/tool + AI percent + total.

    `?project_id=`: lọc theo project — caller phải có membership trên đó.
    Bỏ qua → aggregate global (frontend tự gắn ProjectSelector để khỏi
    lộ data — cross-project global numbers chỉ ý nghĩa cho admin).
    """
    ensure_project_in_scope(user, project_id)
    # V3.7 — khi không chỉ định project_id, scope global theo membership của
    # caller (non-admin). allowed_project_ids trả None cho admin/RBAC-off → global thật.
    scope = allowed_project_ids(user) if project_id is None else None
    return await StatsService(session).overview(project_id=project_id, project_ids=scope)


@router.get("/latest-scan", summary="Stats của run mới nhất có findings")
async def stats_latest_scan(
    project_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_read_access),
) -> dict[str, Any]:
    """Stats của scan mới nhất. Caller phải có membership trên project_id."""
    ensure_project_in_scope(user, project_id)
    scope = allowed_project_ids(user) if project_id is None else None
    return await StatsService(session).latest_scan(project_id=project_id, project_ids=scope)


@router.get("/runs", summary="Pass/fail trend cho last N runs")
async def stats_runs(
    days: int = 30,
    session: AsyncSession = Depends(get_session),
    _: User | None = Depends(require_read_access),
) -> dict[str, Any]:
    """Pass rate + breakdown by day cho window N ngày gần nhất.

    Hits GitHub Actions API directly using the env-bound token, so result
    is the same for all callers — no per-project filtering needed. We
    still gate the endpoint with require_read_access so anonymous callers
    are rejected when ANONYMOUS_READ_ENABLED is off.
    """
    return await StatsService(session).runs(days=days)

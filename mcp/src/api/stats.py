"""Stats endpoints — pre-aggregated counts cho dashboard KPI/trend."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import require_read_access
from ..core.db import get_session
from ..services.stats_service import StatsService

router = APIRouter(
    prefix="/stats", tags=["stats"],
    # V3.3 — every stats endpoint goes through the read kill-switch.
    dependencies=[Depends(require_read_access)],
)


@router.get("/overview", summary="Aggregated KPI cho Overview page")
async def stats_overview(
    project_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Trả về counts theo severity/status/tool + AI percent + total. Auth=none.

    `?project_id=` (V2.9): lọc theo project. Bỏ qua → aggregate toàn hệ thống.
    """
    return await StatsService(session).overview(project_id=project_id)


@router.get("/latest-scan", summary="Stats của run mới nhất có findings")
async def stats_latest_scan(
    project_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Aggregated KPI cho 'scan mới nhất' (run_id mới nhất có findings trong DB).

    Khác với /stats/overview (toàn bộ findings cumulative) — endpoint này scope
    về 1 run duy nhất, dùng cho Dashboard Overview.

    `?project_id=` (V2.9): chỉ xét scan của project đó.
    """
    return await StatsService(session).latest_scan(project_id=project_id)


@router.get("/runs", summary="Pass/fail trend cho last N runs")
async def stats_runs(
    days: int = 30,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Pass rate + breakdown by day cho window N ngày gần nhất.
    Gọi GitHub Actions trực tiếp (không persist).
    """
    return await StatsService(session).runs(days=days)

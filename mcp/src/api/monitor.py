"""Monitor API — V2.4. UptimeCheck list + Alert list + manual ping trigger."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import User, allowed_project_ids, ensure_project_in_scope, require_read_access
from ..core.db import get_session
from ..models.entities import Alert, UptimeCheck
from ..services.monitor import run_monitor_cycle

router = APIRouter(
    prefix="/monitor", tags=["monitor"],
    # V3.5 RBAC audit — every monitor endpoint behind the kill-switch.
    # Previously these were open: anyone could see uptime/alert data even
    # when /findings was locked down. Closes that asymmetry.
    dependencies=[Depends(require_read_access)],
)


@router.get("/uptime")
async def list_uptime(
    project_id: int | None = Query(None),
    hours: int = Query(24, le=168),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_read_access),
) -> dict:
    """Recent uptime checks within the last N hours (default 24, max 168=1week).

    V3.5 — when RBAC is on and a project_id is given, caller must have a
    membership; without project_id, results are silently scoped to the
    caller's memberships (admin sees all).
    """
    ensure_project_in_scope(user, project_id)
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    q = select(UptimeCheck).where(UptimeCheck.checked_at >= cutoff)
    if project_id is not None:
        q = q.where(UptimeCheck.project_id == project_id)
    elif scope is not None:
        q = q.where(UptimeCheck.project_id.in_(scope) if scope else False)
    q = q.order_by(desc(UptimeCheck.checked_at)).limit(1000)
    rows = list((await session.execute(q)).scalars().all())
    return {
        "count": len(rows),
        "hours": hours,
        "items": [
            {
                "id": r.id,
                "project_id": r.project_id,
                "target_url": r.target_url,
                "checked_at": r.checked_at.isoformat(),
                "http_status": r.http_status,
                "response_time_ms": r.response_time_ms,
                "is_up": bool(r.is_up),
                "error_message": r.error_message,
            }
            for r in rows
        ],
    }


@router.get("/summary")
async def uptime_summary(
    hours: int = Query(24, le=168),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Aggregate per-target uptime % for the Monitor tab."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    total_q = (
        select(
            UptimeCheck.target_url,
            func.count(UptimeCheck.id).label("total"),
            func.sum(UptimeCheck.is_up).label("up"),
            func.avg(UptimeCheck.response_time_ms).label("avg_latency"),
        )
        .where(UptimeCheck.checked_at >= cutoff)
        .group_by(UptimeCheck.target_url)
    )
    rows = list((await session.execute(total_q)).all())
    summary = []
    for url, total, up, latency in rows:
        up = int(up or 0)
        total = int(total or 0)
        summary.append({
            "target_url": url,
            "checks": total,
            "up": up,
            "down": total - up,
            "uptime_pct": round((up / total) * 100, 2) if total else 0,
            "avg_latency_ms": int(latency) if latency else None,
        })
    return {"hours": hours, "targets": summary}


@router.get("/alerts")
async def list_alerts(
    kind: str | None = Query(None),
    only_open: bool = Query(False),
    limit: int = Query(50, le=500),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_read_access),
) -> list[dict]:
    """Recent alerts. kind ∈ {down, recovered, cve_new, deploy_failed}.

    V3.5 — non-admin callers only see alerts attached to their member
    projects (or with `project_id IS NULL` for instance-wide ops alerts).
    """
    scope = allowed_project_ids(user)
    q = select(Alert)
    if scope is not None:
        # Allow project_id IS NULL (system-wide alerts) plus rows in scope.
        q = q.where(
            Alert.project_id.is_(None) | Alert.project_id.in_(scope) if scope
            else Alert.project_id.is_(None)
        )
    if kind:
        q = q.where(Alert.kind == kind)
    if only_open:
        q = q.where(Alert.acknowledged_at.is_(None))
    q = q.order_by(desc(Alert.raised_at)).limit(limit)
    rows = list((await session.execute(q)).scalars().all())
    return [
        {
            "id": r.id,
            "project_id": r.project_id,
            "kind": r.kind,
            "severity": r.severity,
            "title": r.title,
            "detail": r.detail,
            "extra": r.extra,
            "raised_at": r.raised_at.isoformat(),
            "notified_at": r.notified_at.isoformat() if r.notified_at else None,
            "acknowledged_at": r.acknowledged_at.isoformat() if r.acknowledged_at else None,
        }
        for r in rows
    ]


@router.post("/alerts/{alert_id}/ack", status_code=204)
async def ack_alert(
    alert_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Acknowledge an open alert so the monitor stops resending."""
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.acknowledged_at is None:
        alert.acknowledged_at = datetime.now(UTC)
        await session.commit()


@router.post("/ping", status_code=202)
async def trigger_ping() -> dict:
    """Manual cycle trigger — useful for demo + debug without waiting interval."""
    count = await run_monitor_cycle()
    return {"checks_executed": count}

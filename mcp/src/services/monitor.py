"""Monitor service — V2.4 uptime check + alert raising.

Pings inheritor staging URLs every MONITOR_INTERVAL_SECONDS. After
MONITOR_DOWN_THRESHOLD consecutive failures, raises a "down" Alert and
fires an email (best-effort). On the next 2xx after a down spell,
raises a "recovered" Alert.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, UTC

import httpx
from sqlalchemy import desc, select

from ..core.config import settings
from ..core.db import AsyncSessionLocal
from ..models.entities import Alert, UptimeCheck
from .smtp_service import (
    format_down_alert,
    format_recovered_alert,
    send_alert_email,
)

log = logging.getLogger(__name__)


def _parse_targets() -> list[tuple[int, str]]:
    """Parse `MONITOR_TARGETS=1:https://a,2:https://b` env var."""
    out: list[tuple[int, str]] = []
    raw = settings.MONITOR_TARGETS or ""
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        pid_str, _, url = entry.partition(":")
        try:
            pid = int(pid_str)
        except ValueError:
            log.warning("Bad MONITOR_TARGETS entry: %s", entry)
            continue
        out.append((pid, url.strip()))
    return out


async def _check_once(project_id: int, url: str) -> UptimeCheck:
    """Ping one URL and persist a single UptimeCheck row.

    Returns the persisted row so the caller can decide whether to alert.
    """
    started = time.perf_counter()
    status = 0
    error: str | None = None
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
            status = resp.status_code
    except Exception as exc:  # noqa: BLE001
        error = str(exc)[:500]

    duration_ms = int((time.perf_counter() - started) * 1000)
    is_up = 200 <= status < 400

    async with AsyncSessionLocal() as session:
        row = UptimeCheck(
            project_id=project_id,
            target_url=url,
            http_status=status,
            response_time_ms=duration_ms,
            is_up=1 if is_up else 0,
            error_message=error,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def _maybe_alert(check: UptimeCheck) -> None:
    """Open a 'down' alert after threshold consecutive fails, or 'recovered'."""
    threshold = settings.MONITOR_DOWN_THRESHOLD

    async with AsyncSessionLocal() as session:
        # Last `threshold` checks for this URL
        recent_q = (
            select(UptimeCheck)
            .where(UptimeCheck.target_url == check.target_url)
            .order_by(desc(UptimeCheck.checked_at))
            .limit(threshold)
        )
        recent = list((await session.execute(recent_q)).scalars().all())

        # Check most recent unresolved 'down' alert for this URL
        last_down_q = (
            select(Alert)
            .where(
                Alert.kind == "down",
                Alert.extra.is_not(None),
            )
            .order_by(desc(Alert.raised_at))
            .limit(5)
        )
        candidate_downs = list((await session.execute(last_down_q)).scalars().all())
        last_down = next(
            (a for a in candidate_downs if (a.extra or {}).get("target_url") == check.target_url),
            None,
        )
        already_alerted = bool(last_down and last_down.acknowledged_at is None)

        if not check.is_up:
            if len(recent) >= threshold and all(not r.is_up for r in recent):
                if already_alerted:
                    return  # already fired, wait for ack
                title = f"Down: {check.target_url}"
                subject, body = format_down_alert(
                    target_url=check.target_url,
                    fail_count=threshold,
                    last_status=check.http_status,
                )
                emailed = send_alert_email(subject=subject, body_html=body)
                alert = Alert(
                    project_id=check.project_id,
                    kind="down",
                    severity="high",
                    title=title,
                    detail=check.error_message,
                    extra={
                        "target_url": check.target_url,
                        "last_status": check.http_status,
                        "fail_count": threshold,
                    },
                    notified_at=datetime.now(UTC) if emailed else None,
                )
                session.add(alert)
                await session.commit()
                log.warning("DOWN alert raised: %s", check.target_url)
            return

        # check.is_up — if there's an open down alert, close it + announce recovered
        if already_alerted and last_down is not None:
            last_down.acknowledged_at = datetime.now(UTC)
            downtime_min = max(
                1,
                int((datetime.now(UTC) - last_down.raised_at).total_seconds() // 60),
            )
            subject, body = format_recovered_alert(
                target_url=check.target_url,
                downtime_minutes=downtime_min,
            )
            emailed = send_alert_email(subject=subject, body_html=body)
            alert = Alert(
                project_id=check.project_id,
                kind="recovered",
                severity="low",
                title=f"Recovered: {check.target_url}",
                detail=f"Back up after ~{downtime_min} min",
                extra={
                    "target_url": check.target_url,
                    "downtime_minutes": downtime_min,
                },
                notified_at=datetime.now(UTC) if emailed else None,
            )
            session.add(alert)
            await session.commit()
            log.info("RECOVERED alert: %s after %d min", check.target_url, downtime_min)


async def run_monitor_cycle() -> int:
    """Run one full cycle of uptime checks. Returns count of checks executed."""
    targets = _parse_targets()
    if not targets:
        return 0
    log.info("Monitor cycle — %d target(s)", len(targets))
    count = 0
    for project_id, url in targets:
        try:
            check = await _check_once(project_id, url)
            await _maybe_alert(check)
            count += 1
        except Exception:  # noqa: BLE001
            log.exception("Monitor failed for %s", url)
    return count


async def monitor_loop() -> None:
    """Background loop — invoked by FastAPI lifespan when MONITOR_ENABLED."""
    interval = max(60, settings.MONITOR_INTERVAL_SECONDS)
    log.info("Monitor loop started: interval=%ds", interval)
    while True:
        try:
            await run_monitor_cycle()
        except Exception:  # noqa: BLE001
            log.exception("Monitor cycle errored")
        await asyncio.sleep(interval)


async def prune_old_checks(days: int = 7) -> int:
    """Delete UptimeCheck rows older than `days`. Returns rows deleted."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    async with AsyncSessionLocal() as session:
        from sqlalchemy import delete as sa_delete
        result = await session.execute(
            sa_delete(UptimeCheck).where(UptimeCheck.checked_at < cutoff)
        )
        await session.commit()
        return result.rowcount or 0

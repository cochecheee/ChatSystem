"""V3.6 — append-only audit log writer.

Privileged actions across the API funnel through `write_audit()` so we
have a single audit trail surviving deletions. Use it from:
  - approve / revoke findings (target_kind="finding")
  - rotate webhook token (target_kind="project")
  - set gate threshold (target_kind="project", payload={old, new})
  - create / delete suppression rule (target_kind="suppression_rule")
  - add / remove project member (target_kind="member", payload={username, role})
  - archive / unarchive project (target_kind="project")

Read-side helpers (`recent_for_project`, `list_by_actor`) for the UI
later — not added until B/C milestones need them.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.entities import AuditLog


async def write_audit(
    session: AsyncSession,
    *,
    actor: str,
    action: str,
    project_id: int | None = None,
    target_kind: str | None = None,
    target_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditLog:
    """Insert one row. Caller controls commit — we don't commit so the
    audit row participates in the same transaction as the action being
    audited (atomic: if the action rolls back, so does the audit row).

    JSON payload: SQLAlchemy default JSON type stringifies None as 'null'
    — pass `None` only when you have no extra context; never pass the
    string 'null'.
    """
    row = AuditLog(
        actor=actor,
        action=action,
        project_id=project_id,
        target_kind=target_kind,
        target_id=target_id,
    )
    if payload is not None:
        row.payload = payload
    session.add(row)
    await session.flush()  # populate row.id without committing
    return row

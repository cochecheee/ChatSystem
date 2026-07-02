"""V3.8 — baseline catch-up: represent every model table in a migration.

Revision ID: f3a8c2d19e74
Revises: bdf2034e591c
Create Date: 2026-06-22

Before this revision several tables — ``users``, ``project_members``,
``suppression_rules``, ``alerts``, ``uptime_checks``, ``command_feedback`` and
the core ``projects`` / ``artifacts`` / ``findings`` / ``app_config`` — existed
ONLY via ``Base.metadata.create_all()`` at startup. They were not represented in
any Alembic revision, so a migration-driven deploy could not build them and the
schema drift went untracked (audit 2026-06-22, CRITICAL).

This revision idempotently brings any database up to the current model schema by
running ``create_all(checkfirst=True)`` against the live connection:

  * on a DB already built by ``create_all`` (the current boot path) it is a
    no-op — every table already exists, so nothing is created;
  * on a migration-only DB it creates the remaining tables.

Driving it from ``Base.metadata`` guarantees the migration can never drift from
the ORM definitions (unlike a hand-copied ``op.create_table`` snapshot). It runs
AFTER the V3.6 revision, which ALTERs ``projects``/``artifacts`` and assumes the
core tables already exist.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "f3a8c2d19e74"
down_revision: Union[str, Sequence[str], None] = "bdf2034e591c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Import inside the function so the model metadata is loaded lazily and the
    # revision stays importable regardless of import order. Importing entities
    # registers every table on Base.metadata.
    from src.core.db import Base
    from src.models import entities as _entities  # noqa: F401 — registers tables

    bind = op.get_bind()
    # checkfirst=True → only missing tables are created; existing ones skipped.
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    # A baseline catch-up is not safely reversible — downgrading would drop the
    # core tables (projects/artifacts/findings) and destroy all data. Intentional
    # no-op; use the explicit INIT_DB_DROP_ALL reset for a full teardown.
    pass

"""V3.6 — pipeline_runs first-class entity, gate policy per project,
webhook deliveries dedup, soft delete on projects, audit log table.

Revision ID: bdf2034e591c
Revises:
Create Date: 2026-05-29

This migration is idempotent: it checks for existing tables/columns before
creating them, so it's safe to run against:
  - a fresh DB (Base.metadata.create_all already made tables → most ops skip)
  - a V3.5 DB (most tables exist, columns/tables added on top)
  - re-runs (already-applied ops detected and skipped)

Backfill at the end groups existing artifacts by (project_id, github_run_id)
and creates one pipeline_runs row per group, then links artifacts.run_id.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "bdf2034e591c"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _table_exists(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    insp = inspect(op.get_bind())
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # 1) pipeline_runs --------------------------------------------------------
    if not _table_exists("pipeline_runs"):
        op.create_table(
            "pipeline_runs",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer,
                      sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("github_run_id", sa.BigInteger, nullable=False),
            sa.Column("github_run_number", sa.Integer, nullable=True),
            sa.Column("workflow_name", sa.String(255), nullable=True),
            sa.Column("branch", sa.String(255), nullable=True),
            sa.Column("head_sha", sa.String(64), nullable=True),
            sa.Column("actor", sa.String(255), nullable=True),
            sa.Column("event", sa.String(50), nullable=True),
            sa.Column("status", sa.String(50), nullable=False,
                      server_default="completed"),
            sa.Column("conclusion", sa.String(50), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("github_run_url", sa.String(1024), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            sa.UniqueConstraint("project_id", "github_run_id",
                                name="uq_pipeline_runs_project_github"),
        )
        op.create_index("ix_pipeline_runs_project_id", "pipeline_runs", ["project_id"])
        op.create_index("ix_pipeline_runs_created_at", "pipeline_runs", ["created_at"])

    # 2) artifacts.run_id ----------------------------------------------------
    if not _column_exists("artifacts", "run_id"):
        # SQLite ALTER TABLE can't add a FK in-place — alembic's batch mode
        # rebuilds the table. We supply explicit FK name so batch mode
        # doesn't bail with "Constraint must have a name".
        with op.batch_alter_table(
            "artifacts",
            naming_convention={
                "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            },
        ) as batch:
            batch.add_column(sa.Column(
                "run_id", sa.Integer,
                sa.ForeignKey(
                    "pipeline_runs.id",
                    name="fk_artifacts_run_id_pipeline_runs",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ))
        op.create_index("ix_artifacts_run_id", "artifacts", ["run_id"])

    # 3) projects gate policy + archive --------------------------------------
    project_cols_to_add = [
        ("gate_critical_threshold", sa.Integer, "0", False),
        ("gate_high_threshold", sa.Integer, "5", False),
        ("archived_at", sa.DateTime(timezone=True), None, True),
    ]
    for col_name, col_type, default, nullable in project_cols_to_add:
        if _column_exists("projects", col_name):
            continue
        with op.batch_alter_table("projects") as batch:
            kwargs = dict(nullable=nullable)
            if default is not None:
                kwargs["server_default"] = default
            batch.add_column(sa.Column(col_name, col_type, **kwargs))

    # 4) webhook_deliveries --------------------------------------------------
    if not _table_exists("webhook_deliveries"):
        op.create_table(
            "webhook_deliveries",
            sa.Column("delivery_id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.Integer,
                      sa.ForeignKey("projects.id"), nullable=True),
            sa.Column("github_run_id", sa.BigInteger, nullable=True),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            sa.Column("body_sha256", sa.String(64), nullable=True),
            sa.Column("outcome", sa.String(40), nullable=False,
                      server_default="accepted"),
            sa.Column("detail", sa.Text, nullable=True),
        )
        op.create_index("ix_webhook_deliveries_project_id",
                        "webhook_deliveries", ["project_id"])
        op.create_index("ix_webhook_deliveries_received_at",
                        "webhook_deliveries", ["received_at"])

    # 5) audit_log -----------------------------------------------------------
    if not _table_exists("audit_log"):
        op.create_table(
            "audit_log",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("actor", sa.String(255), nullable=False),
            sa.Column("action", sa.String(64), nullable=False),
            sa.Column("project_id", sa.Integer,
                      sa.ForeignKey("projects.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("target_kind", sa.String(32), nullable=True),
            sa.Column("target_id", sa.BigInteger, nullable=True),
            sa.Column("payload", sa.JSON, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
        )
        op.create_index("ix_audit_log_actor", "audit_log", ["actor"])
        op.create_index("ix_audit_log_action", "audit_log", ["action"])
        op.create_index("ix_audit_log_project_id", "audit_log", ["project_id"])
        op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])

    # 6) Backfill pipeline_runs from existing artifacts ----------------------
    # Group existing artifacts by (project_id, github_run_id), create one
    # pipeline_runs row per group with conservative defaults, then link.
    # We only backfill when pipeline_runs is empty (avoid re-running after
    # a partial first attempt). Idempotent because of UNIQUE constraint.
    backfill_check = bind.execute(sa.text(
        "SELECT COUNT(*) FROM pipeline_runs"
    )).scalar()
    if backfill_check == 0:
        # Find the distinct (project_id, github_run_id) pairs with at least
        # one artifact AND github_run_id IS NOT NULL.
        bind.execute(sa.text("""
            INSERT INTO pipeline_runs (
                project_id, github_run_id, status, started_at, created_at, updated_at
            )
            SELECT
                project_id,
                github_run_id,
                'completed',
                MIN(created_at),
                MIN(created_at),
                MIN(created_at)
            FROM artifacts
            WHERE github_run_id IS NOT NULL
            GROUP BY project_id, github_run_id
        """))

        # Link artifacts.run_id to the new pipeline_runs.id.
        bind.execute(sa.text("""
            UPDATE artifacts
            SET run_id = (
                SELECT pr.id FROM pipeline_runs pr
                WHERE pr.project_id = artifacts.project_id
                  AND pr.github_run_id = artifacts.github_run_id
            )
            WHERE github_run_id IS NOT NULL
        """))


# ---------------------------------------------------------------------------
# Downgrade — best-effort. Drops the new tables/columns but doesn't restore
# data that was backfilled into pipeline_runs. Re-running upgrade will
# re-backfill from artifacts.github_run_id (which we deliberately keep as a
# denormalized cache for exactly this reason).
# ---------------------------------------------------------------------------

def downgrade() -> None:
    if _table_exists("audit_log"):
        op.drop_index("ix_audit_log_created_at", table_name="audit_log")
        op.drop_index("ix_audit_log_project_id", table_name="audit_log")
        op.drop_index("ix_audit_log_action", table_name="audit_log")
        op.drop_index("ix_audit_log_actor", table_name="audit_log")
        op.drop_table("audit_log")

    if _table_exists("webhook_deliveries"):
        op.drop_index("ix_webhook_deliveries_received_at", table_name="webhook_deliveries")
        op.drop_index("ix_webhook_deliveries_project_id", table_name="webhook_deliveries")
        op.drop_table("webhook_deliveries")

    for col in ("archived_at", "gate_high_threshold", "gate_critical_threshold"):
        if _column_exists("projects", col):
            with op.batch_alter_table("projects") as batch:
                batch.drop_column(col)

    if _column_exists("artifacts", "run_id"):
        op.drop_index("ix_artifacts_run_id", table_name="artifacts")
        with op.batch_alter_table("artifacts") as batch:
            batch.drop_column("run_id")

    if _table_exists("pipeline_runs"):
        op.drop_index("ix_pipeline_runs_created_at", table_name="pipeline_runs")
        op.drop_index("ix_pipeline_runs_project_id", table_name="pipeline_runs")
        op.drop_table("pipeline_runs")

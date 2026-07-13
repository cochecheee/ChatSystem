"""Portable data migration: local MySQL/MariaDB  ->  Render Postgres.

MySQL and Postgres dumps are NOT cross-loadable (backticks, AUTO_INCREMENT,
JSON syntax, sequence handling all differ), so we copy row-by-row through
SQLAlchemy Core using the app's own typed table metadata. That makes the copy
dialect-agnostic: types, JSON, and datetimes are (de)serialised per-dialect.

What it copies (FK-safe order): projects, pipeline_runs, artifacts, findings,
finding_actions, command_feedback, suppression_rules, project_members,
webhook_deliveries, uptime_checks, alerts, audit_log.

What it SKIPS: `users` (Render seeds them idempotently at boot) and `app_config`
(per-instance). Per-project secrets (github_token, gemini_api_key) are NULLed on
copy so Render falls back to its env secrets (no token lands in Postgres).

Usage (run from chat-system/mcp with the venv):
    # 1) validate the read/transform half against local MySQL (no writes):
    SOURCE_URL="mysql+asyncmy://root:@127.0.0.1:3306/chat_system" \\
        ./.venv/Scripts/python.exe scripts/migrate_data_to_render.py --dry-run

    # 2) real migration into Render Postgres (get the *External* URL from the
    #    Render dashboard -> mcp-db -> "External Database URL"):
    SOURCE_URL="mysql+asyncmy://root:@127.0.0.1:3306/chat_system" \\
    DEST_URL="postgresql+asyncpg://mcp:PASS@HOST.singapore-postgres.render.com/mcp" \\
        ./.venv/Scripts/python.exe scripts/migrate_data_to_render.py --wipe

`--wipe` clears the destination tables (reverse FK order) first so the run is
repeatable. Postgres id sequences are reset to MAX(id) afterwards.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import ssl
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.abspath("."))  # make `src` importable when run from mcp/

from sqlalchemy import delete, insert, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from src.models.entities import (  # noqa: E402
    Alert,
    Artifact,
    AuditLog,
    Base,
    CommandFeedback,
    Finding,
    FindingAction,
    PipelineRun,
    Project,
    ProjectMember,
    SuppressionRule,
    UptimeCheck,
    WebhookDelivery,
)

# Parents first — every FK target precedes its referrers.
ORDER = [
    Project,
    PipelineRun,
    Artifact,
    Finding,
    FindingAction,
    CommandFeedback,
    SuppressionRule,
    ProjectMember,
    WebhookDelivery,
    UptimeCheck,
    Alert,
    AuditLog,
]

# Columns blanked on copy so Render uses its own env secrets, never the DB.
# Empty string (not NULL) because these columns are NOT NULL in the Render
# schema; the app treats "" as "no per-project creds -> use env fallback".
BLANK_ON_COPY = {"projects": ("github_token", "gemini_api_key")}


def _norm(url: str) -> str:
    """Rewrite vendor URLs to SQLAlchemy async dialects (same rule as config.py)."""
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    if url.startswith("mysql://") and "+asyncmy" not in url and "+aiomysql" not in url:
        return "mysql+asyncmy://" + url[len("mysql://"):]
    return url


def _make_engine(url: str):
    """Build an async engine; for Render external Postgres add an SSL context
    (connections require SSL) and drop psycopg-style ?sslmode= which asyncpg
    can't parse."""
    url = _norm(url)
    connect_args: dict = {}
    if url.startswith("postgresql+asyncpg://"):
        if "?" in url:
            url = url.split("?", 1)[0]
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        connect_args = {"ssl": ctx}
    return create_async_engine(url, connect_args=connect_args)


def _normalise(row: dict, table_name: str) -> dict:
    """Naive datetimes -> UTC-aware (Postgres timestamptz rejects/So misreads
    naive values that MySQL DATETIME stored bare); NULL sensitive columns."""
    out = dict(row)
    for k, v in out.items():
        if isinstance(v, datetime) and v.tzinfo is None:
            out[k] = v.replace(tzinfo=UTC)
    for col in BLANK_ON_COPY.get(table_name, ()):
        if col in out:
            out[col] = ""
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="read+transform+count only, no writes")
    ap.add_argument("--wipe", action="store_true", help="clear destination tables first (reverse FK order)")
    args = ap.parse_args()

    source_url = os.environ.get("SOURCE_URL", "mysql+asyncmy://root:@127.0.0.1:3306/chat_system")
    dest_url = os.environ.get("DEST_URL", "")
    if not args.dry_run and not dest_url:
        sys.exit("DEST_URL is required (unless --dry-run). See the module docstring.")

    src = _make_engine(source_url)
    dst = _make_engine(dest_url) if dest_url else None

    # Read + transform every table from the source.
    payload: dict[str, list[dict]] = {}
    async with src.connect() as sconn:
        for model in ORDER:
            t = model.__table__
            rows = (await sconn.execute(select(t))).mappings().all()
            payload[t.name] = [_normalise(dict(r), t.name) for r in rows]
    await src.dispose()

    total = sum(len(v) for v in payload.values())
    for model in ORDER:
        print(f"  {model.__table__.name:20s} {len(payload[model.__table__.name]):>6d} rows")
    print(f"  {'TOTAL':20s} {total:>6d} rows")

    if args.dry_run or dst is None:
        print("\n[dry-run] source read OK — no writes performed.")
        return

    # Ensure schema exists (Render's app also runs Alembic at boot; create_all
    # is a harmless no-op if the tables are already there).
    async with dst.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    if args.wipe:
        async with dst.begin() as conn:
            for model in reversed(ORDER):
                await conn.execute(delete(model.__table__))
        print("[wipe] destination tables cleared.")

    # Insert parents -> children.
    async with dst.begin() as conn:
        for model in ORDER:
            t = model.__table__
            rows = payload[t.name]
            if rows:
                await conn.execute(insert(t), rows)
            print(f"  inserted {t.name}: {len(rows)}")

    # Reset Postgres identity sequences to MAX(id) so future inserts don't collide.
    async with dst.begin() as conn:
        for model in ORDER:
            t = model.__table__
            if "id" in t.c and t.c["id"].autoincrement:
                await conn.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{t.name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {t.name}), 1))"
                ))
    await dst.dispose()
    print("\n[done] migration complete; sequences reset.")


if __name__ == "__main__":
    asyncio.run(main())

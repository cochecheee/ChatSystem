import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    # MySQL CREATE TABLE dùng utf8mb4 + utf8mb4_unicode_ci (XAMPP MariaDB
    # 10.x compatible). Postgres/SQLite ignore các option `mysql_*` này.
    __table_args__ = {
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_ci",
    }


def _engine_connect_args(url: str) -> dict:
    """MySQL không có TIMESTAMP WITH TIME ZONE — set session tz UTC để
    `DateTime(timezone=True)` columns lưu UTC nhất quán, không phụ thuộc
    server `time_zone` global. Postgres/SQLite không cần (đã native).
    """
    if url.startswith(("mysql+", "mysql:")):
        return {"init_command": "SET time_zone='+00:00'"}
    return {}


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_ENV == "development",
    connect_args=_engine_connect_args(settings.DATABASE_URL),
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        # Auto-drop hatch: drop+recreate Postgres tables when an older schema
        # is detected. Two known migrations:
        #   1. TIMESTAMP -> TIMESTAMP WITH TIME ZONE (DT_TZ migration)
        #   2. INTEGER  -> BIGINT  on github run-id columns (INT4 overflow)
        # SQLite stores integers/timestamps dynamically so skips both checks.
        force_drop = os.environ.get("INIT_DB_DROP_ALL") == "1"
        if force_drop:
            reason = "INIT_DB_DROP_ALL"
        elif await conn.run_sync(_needs_tz_migration):
            reason = "TZ migration detected"
        elif await conn.run_sync(_needs_bigint_migration):
            reason = "BIGINT migration detected"
        else:
            reason = None

        if reason is not None:
            log.warning(
                "Dropping all tables (reason=%s) — recreating with current schema",
                reason,
            )
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_schema)

    # V3.6 — also run pending Alembic migrations. Idempotent: alembic stamps
    # the DB after each upgrade, so on subsequent boots this returns
    # immediately. Disabled in tests (SKIP_ALEMBIC=1) since the test suite
    # uses in-memory SQLite that's recreated per-test and Base.metadata.
    # create_all() above already covers the schema.
    if os.environ.get("SKIP_ALEMBIC") != "1":
        try:
            await _run_alembic_upgrade()
        except Exception:  # noqa: BLE001
            log.exception("Alembic upgrade failed — continuing without migration")


def _pg_column_data_type(sync_conn, table: str, column: str) -> str | None:
    """Return the canonical Postgres `data_type` for a column, or None if
    the table/column doesn't exist. Goes through information_schema so we
    get the truthful DB type string ("timestamp with time zone", "bigint",
    "integer", ...) — SQLAlchemy's reflected column.type stringifies as
    "TIMESTAMP" or "INTEGER" regardless of the underlying variant, which
    previously caused these migration checks to fire on every boot.
    """
    from sqlalchemy import text

    row = sync_conn.execute(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).first()
    return row[0].lower() if row else None


def _needs_tz_migration(sync_conn) -> bool:
    """Return True iff Postgres has projects.created_at as the naive
    `timestamp without time zone` variant. Schema predates the DT_TZ
    rewrite — drop+recreate once so the tz-aware columns apply.
    """
    if sync_conn.dialect.name != "postgresql":
        return False
    dtype = _pg_column_data_type(sync_conn, "projects", "created_at")
    if dtype is None:
        return False  # fresh DB; create_all handles it
    return "with time zone" not in dtype


def _needs_bigint_migration(sync_conn) -> bool:
    """Return True iff Postgres has artifacts.github_run_id as INTEGER (INT4)
    instead of BIGINT. GitHub run IDs already exceed INT4 max (~2.1B), so any
    insert overflows. SQLite reports the column as INTEGER for both; ignore.
    """
    if sync_conn.dialect.name != "postgresql":
        return False
    dtype = _pg_column_data_type(sync_conn, "artifacts", "github_run_id")
    if dtype is None:
        return False
    return dtype != "bigint"


def _migrate_schema(sync_conn) -> None:
    """Add missing columns to existing tables — idempotent, safe to run on every startup."""
    from sqlalchemy import inspect, text

    inspector = inspect(sync_conn)
    tables = set(inspector.get_table_names())

    def add_columns(table: str, cols: list[tuple[str, str]]) -> None:
        if table not in tables:
            return
        existing = {c["name"] for c in inspector.get_columns(table)}
        for col_name, col_type in cols:
            if col_name not in existing:
                sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))

    add_columns("findings", [
        ("justification",        "TEXT"),
        ("approved_by",          "VARCHAR(255)"),
        ("approved_at",          "DATETIME"),
        ("revoke_justification", "TEXT"),
        ("revoked_by",           "VARCHAR(255)"),
        ("revoked_at",           "DATETIME"),
    ])

    add_columns("artifacts", [
        ("github_run_id", "INTEGER"),
    ])

    add_columns("projects", [
        # V3.5 — per-project webhook token. Default "" so the existing
        # global CI_WEBHOOK_TOKEN fallback keeps working until each
        # project rotates one in.
        ("webhook_token", "VARCHAR(500) NOT NULL DEFAULT ''"),
    ])


async def _run_alembic_upgrade() -> None:
    """Apply pending Alembic migrations programmatically.

    Run inside `init_db()` so a fresh container `docker run` brings the
    schema up to date before serving requests. The Alembic config file
    lives at `mcp/alembic.ini`; env.py wires it to the same DATABASE_URL.

    For new DBs where `create_all()` already produced the current schema,
    `alembic upgrade head` is a no-op (the version table is created and
    stamped). On older DBs with pre-V3.6 schema, it adds new tables /
    columns and backfills pipeline_runs.
    """
    import asyncio
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    repo_root = Path(__file__).resolve().parents[2]
    ini_path = repo_root / "alembic.ini"
    if not ini_path.exists():
        log.warning("alembic.ini not found at %s — skipping", ini_path)
        return

    def _run() -> None:
        cfg = Config(str(ini_path))
        command.upgrade(cfg, "head")

    # Alembic command.upgrade is sync — push to a worker thread so the
    # event loop stays responsive while migrations apply.
    await asyncio.to_thread(_run)
    log.info("Alembic upgrade head completed")


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

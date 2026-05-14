import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_ENV == "development",
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


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

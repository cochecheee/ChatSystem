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


def _needs_tz_migration(sync_conn) -> bool:
    """Return True iff connection is Postgres AND projects.created_at exists
    as `timestamp without time zone`. Means schema predates the DT_TZ change
    and we need a one-shot drop+recreate.
    """
    if sync_conn.dialect.name != "postgresql":
        return False
    from sqlalchemy import inspect

    inspector = inspect(sync_conn)
    if "projects" not in inspector.get_table_names():
        return False  # fresh DB, create_all will set correct types
    for col in inspector.get_columns("projects"):
        if col["name"] == "created_at":
            col_type = str(col["type"]).upper()
            # SQLAlchemy returns "TIMESTAMP" for naive, "TIMESTAMP WITH TIME ZONE" for aware
            return "WITH TIME ZONE" not in col_type
    return False


def _needs_bigint_migration(sync_conn) -> bool:
    """Return True iff Postgres has artifacts.github_run_id as INTEGER (INT4)
    instead of BIGINT. GitHub run IDs already exceed INT4 max (~2.1B), so any
    insert overflows. SQLite reports the column as INTEGER for both; ignore.
    """
    if sync_conn.dialect.name != "postgresql":
        return False
    from sqlalchemy import inspect

    inspector = inspect(sync_conn)
    if "artifacts" not in inspector.get_table_names():
        return False
    for col in inspector.get_columns("artifacts"):
        if col["name"] == "github_run_id":
            col_type = str(col["type"]).upper()
            return "BIGINT" not in col_type
    return False


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

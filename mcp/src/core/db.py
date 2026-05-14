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
        # One-shot reset hatch — set INIT_DB_DROP_ALL=1 on Render after a
        # schema change (e.g. DateTime → DateTime(timezone=True)). Unset
        # immediately after the next deploy so we don't nuke real data.
        if os.environ.get("INIT_DB_DROP_ALL") == "1":
            log.warning("INIT_DB_DROP_ALL=1 — dropping all tables before recreate")
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_schema)


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

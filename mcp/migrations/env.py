"""Alembic env — wired to use the project's settings + Base metadata.

Run from `mcp/` root:
    alembic upgrade head        # apply pending migrations
    alembic revision -m "..."   # create empty revision
    alembic revision --autogenerate -m "..."   # diff models vs DB, generate revision

Connection: reads DATABASE_URL from src.core.config.settings (which itself
reads .env). Override per-invocation with:
    alembic -x url=sqlite+aiosqlite:///./other.db upgrade head

The Postgres URL on Render is `postgresql://...` (no `+asyncpg`); the
async engine adapter we use in src.core.db rewrites it. Alembic creates
its own engine here, so we rewrite the same way before handing it to
async_engine_from_config.
"""
from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Make `src.*` importable when running `alembic` from mcp/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import settings  # noqa: E402
from src.core.db import Base  # noqa: E402
from src.models import entities as _entities  # noqa: F401, E402  — register tables on Base.metadata

config = context.config

# Honor -x url=... override; else pull from settings + asyncpg rewrite.
x_args = context.get_x_argument(as_dictionary=True)
db_url = x_args.get("url") or settings.DATABASE_URL
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Offline mode — emit SQL without DB connection."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # SQLite needs batch for ALTER TABLE
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

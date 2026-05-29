"""Verify row count parity giữa Render Postgres và local MySQL."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.models import entities as _entities  # noqa: F401
from src.models.entities import (  # noqa: E402
    Alert, AppConfig, Artifact, CommandFeedback, Finding, Project,
    ProjectMember, SuppressionRule, UptimeCheck,
)

TABLES = [
    Project, Artifact, Finding, AppConfig, UptimeCheck,
    Alert, CommandFeedback, ProjectMember, SuppressionRule,
]


def _norm(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


async def count(engine, Model) -> int:
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as s:
        r = await s.execute(select(sa_func.count()).select_from(Model))
        return r.scalar() or 0


async def main() -> None:
    pg_url = _norm(os.environ.get("PG_SOURCE_URL", "").strip())
    if not pg_url:
        print("FAIL: PG_SOURCE_URL not set")
        return

    from src.core.config import settings
    mysql_url = settings.DATABASE_URL

    src = create_async_engine(pg_url, echo=False)
    dst = create_async_engine(
        mysql_url, echo=False,
        connect_args={"init_command": "SET time_zone='+00:00'"},
    )

    print(f"{'table':<22} {'render':>10} {'mysql':>10}  status")
    print("-" * 56)
    total_diff = 0
    for Model in TABLES:
        src_n = await count(src, Model)
        dst_n = await count(dst, Model)
        status = "OK" if src_n == dst_n else f"DIFF {dst_n - src_n:+d}"
        if src_n != dst_n:
            total_diff += abs(dst_n - src_n)
        print(f"{Model.__tablename__:<22} {src_n:>10} {dst_n:>10}  {status}")

    print("-" * 56)
    if total_diff == 0:
        print("All tables match.")
    else:
        print(f"Mismatch total: {total_diff} rows")


if __name__ == "__main__":
    asyncio.run(main())

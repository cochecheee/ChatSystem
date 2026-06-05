"""One-off: dump Render Postgres schema để chẩn đoán deploy."""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _norm(u: str) -> str:
    if u.startswith("postgres://"):
        return "postgresql+asyncpg://" + u[len("postgres://"):]
    if u.startswith("postgresql://") and "+asyncpg" not in u:
        return "postgresql+asyncpg://" + u[len("postgresql://"):]
    return u


async def main():
    url = _norm(os.environ.get("PG_SOURCE_URL", "").strip())
    if not url:
        print("PG_SOURCE_URL missing")
        return
    eng = create_async_engine(url, echo=False)
    async with eng.connect() as c:
        r = await c.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"))
        tables = [row[0] for row in r.all()]
        print("Tables (" + str(len(tables)) + "):")
        for t in tables:
            print(" -", t)
        print()
        r = await c.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='projects' ORDER BY ordinal_position"
        ))
        print("projects columns:")
        for col, dt in r.all():
            print(f"  {col:<30} {dt}")
        print()
        try:
            r = await c.execute(text("SELECT version_num FROM alembic_version"))
            v = r.scalar()
            print(f"alembic_version: {v}")
        except Exception as e:
            print(f"alembic_version: NOT PRESENT ({e})")


if __name__ == "__main__":
    asyncio.run(main())

"""Add 3 missing V3.6 columns vào Render Postgres `projects` table.

Alembic upgrade head không stamp được vì create_table dùng cho các bảng
mới (pipeline_runs / audit_log / webhook_deliveries) clash với create_all().
Migration script idempotent, nhưng vì alembic không chạy nổi step 1, các
ALTER ở step sau không apply.

Script này:
1. ALTER TABLE projects ADD COLUMN cho 3 cột thiếu (idempotent — check info_schema).
2. Stamp alembic_version = bdf2034e591c để alembic.upgrade.head() return immediate
   ở lần boot tiếp theo.
"""
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


ADDS = [
    # (col_name, sql_type, default_sql, nullable)
    ("gate_critical_threshold", "INTEGER", "0", False),
    ("gate_high_threshold",     "INTEGER", "5", False),
    ("archived_at",             "TIMESTAMP WITH TIME ZONE", None, True),
]

ALEMBIC_REVISION = "bdf2034e591c"


async def main():
    url = _norm(os.environ.get("PG_SOURCE_URL", "").strip())
    if not url:
        print("PG_SOURCE_URL missing")
        return
    eng = create_async_engine(url, echo=False)
    async with eng.begin() as c:
        for col, typ, default, nullable in ADDS:
            r = await c.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='projects' AND column_name=:c"
            ), {"c": col})
            if r.first():
                print(f"  skip {col} — already exists")
                continue
            null_clause = "NULL" if nullable else "NOT NULL"
            default_clause = f"DEFAULT {default}" if default is not None else ""
            sql = f"ALTER TABLE projects ADD COLUMN {col} {typ} {null_clause} {default_clause}".strip()
            print(f"  EXEC: {sql}")
            await c.execute(text(sql))

        # Stamp alembic
        r = await c.execute(text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='alembic_version'"
        ))
        if not r.first():
            print("  CREATE alembic_version table")
            await c.execute(text(
                "CREATE TABLE alembic_version ("
                "version_num VARCHAR(32) NOT NULL, "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
            ))
            await c.execute(text(
                "INSERT INTO alembic_version (version_num) VALUES (:v)"
            ), {"v": ALEMBIC_REVISION})
            print(f"  STAMPED alembic to {ALEMBIC_REVISION}")
        else:
            print("  alembic_version table already exists")

    print()
    print("DONE - 3 columns added (if missing) + alembic stamped.")
    print("Next /projects request should return 200.")


if __name__ == "__main__":
    asyncio.run(main())

"""One-shot data sync: Render Postgres → local MySQL.

Đọc Render Postgres qua asyncpg, ghi vào local MySQL qua asyncmy. Cùng
SQLAlchemy ORM model nên không cần transform SQL hoặc CSV.

Usage:
    set PG_SOURCE_URL=postgres://mcp:xxx@dpg-xxx-singapore.render.com/mcp_xxx
    .venv\\Scripts\\python.exe scripts/sync_render_to_local.py

Idempotency:
    - Local MySQL table phải tồn tại (chạy init_db trước).
    - Script wipe table local trước khi insert (truncate → fresh copy).
    - Order theo dependency FK: projects → artifacts → findings → các bảng còn lại.
    - Hoàn toàn an toàn re-run.

Side-effects:
    - Bảng local sẽ bị xoá sạch trước khi sync — KHÔNG dùng cho local có data riêng.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Add parent dir to path để import src.*
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.models import entities as _entities  # noqa: F401 - register
from src.models.entities import (
    Alert,
    AppConfig,
    Artifact,
    CommandFeedback,
    Finding,
    Project,
    ProjectMember,
    SuppressionRule,
    UptimeCheck,
)

# Order matters: dependency-free → dependent. FK constraint enforce thứ tự này.
SYNC_ORDER = [
    Project,
    Artifact,
    Finding,
    AppConfig,
    UptimeCheck,
    Alert,
    CommandFeedback,
    ProjectMember,
    SuppressionRule,
]


def _normalize_pg(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


async def main() -> None:
    pg_url = os.environ.get("PG_SOURCE_URL", "").strip()
    if not pg_url:
        print("FAIL: env PG_SOURCE_URL chưa set.")
        print("Set rồi run lại:")
        print('  $env:PG_SOURCE_URL="postgres://mcp:xxx@..."')
        return

    pg_url = _normalize_pg(pg_url)

    # Local MySQL — đọc DATABASE_URL từ .env qua settings
    from src.core.config import settings
    mysql_url = settings.DATABASE_URL
    if not mysql_url.startswith("mysql+"):
        print(f"FAIL: DATABASE_URL local không phải MySQL ({mysql_url[:30]}...)")
        return

    print(f"SOURCE: {pg_url.split('@')[0]}@***")
    print(f"TARGET: {mysql_url.split('@')[0]}@***")
    print()

    src_engine = create_async_engine(pg_url, echo=False)
    dst_engine = create_async_engine(
        mysql_url,
        echo=False,
        connect_args={"init_command": "SET time_zone='+00:00'"},
    )
    SrcSession = async_sessionmaker(src_engine, expire_on_commit=False)
    DstSession = async_sessionmaker(dst_engine, expire_on_commit=False)

    # Test connect 2 phía
    try:
        async with src_engine.connect() as c:
            r = await c.execute(text("SELECT version()"))
            print(f"SRC OK: {r.scalar()[:60]}")
    except Exception as e:
        print(f"SRC FAIL: {e}")
        return

    try:
        async with dst_engine.connect() as c:
            r = await c.execute(text("SELECT VERSION()"))
            print(f"DST OK: {r.scalar()}")
    except Exception as e:
        print(f"DST FAIL: {e}")
        return

    print()
    print("=" * 60)

    # Sync từng bảng
    total_rows = 0
    for Model in SYNC_ORDER:
        table = Model.__tablename__
        async with SrcSession() as src:
            result = await src.execute(select(Model))
            rows = result.scalars().all()

        if not rows:
            print(f"  {table:<22} [empty]")
            continue

        # Wipe target. FK off để xoá theo thứ tự ngược cũng được.
        async with DstSession() as dst:
            await dst.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            await dst.execute(text(f"DELETE FROM {table}"))
            await dst.commit()

        # Insert. Detach rows từ src session, re-attach vào dst.
        async with DstSession() as dst:
            await dst.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            for r in rows:
                # Build kwargs từ column attrs để tránh dính session state
                kwargs = {
                    col.name: getattr(r, col.name)
                    for col in Model.__table__.columns
                }
                new_obj = Model(**kwargs)
                dst.add(new_obj)
            await dst.commit()
            # Re-enable FK trên session sau (mỗi session reset)

        print(f"  {table:<22} synced {len(rows)} rows")
        total_rows += len(rows)

    # Reset autoincrement counter để insert mới không clash với id đã copy
    async with DstSession() as dst:
        for Model in SYNC_ORDER:
            t = Model.__tablename__
            try:
                r = await dst.execute(text(f"SELECT MAX(id) FROM {t}"))
                max_id = r.scalar()
                if max_id is not None:
                    await dst.execute(
                        text(f"ALTER TABLE {t} AUTO_INCREMENT={max_id + 1}")
                    )
            except Exception:
                # Bảng không có id (vd. app_config) — bỏ qua
                pass
        await dst.commit()

    print()
    print(f"DONE - total {total_rows} rows synced.")


if __name__ == "__main__":
    asyncio.run(main())

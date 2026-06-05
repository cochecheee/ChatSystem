"""SQLite migration: Project multi-tenant columns (Day 2).

Adds the new Project columns introduced by Day 2 (multi-tenant backend).
Idempotent — safe to run multiple times. Reads existing settings from
.env and backfills the first row so a single-tenant DB keeps working
without manual edits.

Usage:
    python -m scripts.migrate_v2

Safe to run while the server is stopped. Re-running is a no-op.
"""
from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

from sqlalchemy import select, text

from src.core.config import settings
from src.core.db import AsyncSessionLocal, engine
from src.models.entities import Project

_NEW_COLUMNS: dict[str, str] = {
    "github_owner":          "VARCHAR(255) NOT NULL DEFAULT ''",
    "github_repo":           "VARCHAR(255) NOT NULL DEFAULT ''",
    "github_token":          "VARCHAR(500) NOT NULL DEFAULT ''",
    "gemini_api_key":        "VARCHAR(500) NOT NULL DEFAULT ''",
    "gemini_model":          "VARCHAR(100) NOT NULL DEFAULT ''",
    "artifact_profile":      "VARCHAR(64)  NOT NULL DEFAULT 'github-actions-default'",
    "polling_workflow_name": "VARCHAR(255) NOT NULL DEFAULT 'CI Workflow'",
    "polling_branch":        "VARCHAR(255) NOT NULL DEFAULT 'main'",
    "active":                "INTEGER NOT NULL DEFAULT 1",
}


async def _existing_columns(conn) -> set[str]:
    rows = await conn.execute(text("PRAGMA table_info(projects)"))
    return {row[1] for row in rows.fetchall()}


async def add_missing_columns() -> list[str]:
    added: list[str] = []
    async with engine.begin() as conn:
        existing = await _existing_columns(conn)
        for col, ddl in _NEW_COLUMNS.items():
            if col in existing:
                continue
            await conn.execute(text(f"ALTER TABLE projects ADD COLUMN {col} {ddl}"))
            added.append(col)
    return added


async def backfill_first_row_from_env() -> bool:
    """If a single-tenant Project row exists with empty creds, fill from .env."""
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(select(Project))).scalars().all()
        if not rows:
            return False
        # Backfill any row whose owner/repo is blank.
        changed = False
        for p in rows:
            if not p.github_owner and settings.GITHUB_OWNER:
                p.github_owner = settings.GITHUB_OWNER
                changed = True
            if not p.github_repo and settings.GITHUB_REPO:
                p.github_repo = settings.GITHUB_REPO
                changed = True
            if not p.github_token and settings.GITHUB_TOKEN:
                p.github_token = settings.GITHUB_TOKEN
                changed = True
            if not p.gemini_api_key and settings.GEMINI_API_KEY:
                p.gemini_api_key = settings.GEMINI_API_KEY
                changed = True
            if not p.gemini_model:
                p.gemini_model = settings.GEMINI_MODEL
                changed = True
            # Parse owner/repo from github_url if env didn't have them.
            if (not p.github_owner or not p.github_repo) and p.github_url:
                parsed = urlparse(p.github_url)
                parts = [x for x in parsed.path.split("/") if x]
                if len(parts) >= 2:
                    if not p.github_owner:
                        p.github_owner = parts[0]
                        changed = True
                    if not p.github_repo:
                        p.github_repo = parts[1]
                        changed = True
        if changed:
            await s.commit()
        return changed


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("=== migrate_v2: add multi-tenant Project columns ===")
    added = await add_missing_columns()
    if added:
        print(f"Added columns: {', '.join(added)}")
    else:
        print("All columns already present.")

    print("Backfilling first row from .env (if any)…")
    if await backfill_first_row_from_env():
        print("First-row credentials backfilled.")
    else:
        print("Nothing to backfill.")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python
"""Fix a mistyped GitHub repo slug on a Project row (e.g. demi-datn -> demo-datn).

Only touches the PLAINTEXT location fields (github_url / github_owner /
github_repo). Sensitive creds (github_token/gemini_api_key/webhook_token) are
Fernet-encrypted and are NOT changed here.

Dry-run by default — prints the before/after and exits without writing. Add
--apply to commit. Run from the mcp/ directory with the app's venv:

    .venv/Scripts/python.exe scripts/fix_project_repo_slug.py            # preview
    .venv/Scripts/python.exe scripts/fix_project_repo_slug.py --apply    # commit

    # target one project explicitly, or a different typo:
    ... scripts/fix_project_repo_slug.py --project-id 11 --from demi-datn --to demo-datn --apply
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from src.core.db import AsyncSessionLocal  # noqa: E402
from src.models.entities import Project  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser(description="Fix a mistyped repo slug on a Project.")
    ap.add_argument("--project-id", type=int, default=None, help="target one project by id")
    ap.add_argument("--from", dest="frm", default="demi-datn", help="wrong substring")
    ap.add_argument("--to", dest="to", default="demo-datn", help="correct substring")
    ap.add_argument("--apply", action="store_true", help="commit (default: dry-run)")
    args = ap.parse_args()

    async with AsyncSessionLocal() as s:
        if args.project_id is not None:
            p = await s.get(Project, args.project_id)
            targets = [p] if p is not None else []
        else:
            rows = (await s.execute(select(Project))).scalars().all()
            targets = [
                p for p in rows
                if args.frm in (p.github_url or "") or args.frm in (p.github_repo or "")
            ]

        if not targets:
            print(f"No project matches '{args.frm}'. Nothing to do.")
            return 0

        changed = 0
        for p in targets:
            new_url = (p.github_url or "").replace(args.frm, args.to)
            new_owner = (p.github_owner or "").replace(args.frm, args.to)
            new_repo = (p.github_repo or "").replace(args.frm, args.to)
            print(f"\nProject #{p.id} ({p.name})")
            print(f"  github_url  : {p.github_url!r}  ->  {new_url!r}")
            print(f"  github_owner: {p.github_owner!r}  ->  {new_owner!r}")
            print(f"  github_repo : {p.github_repo!r}  ->  {new_repo!r}")

            if new_url == p.github_url and new_owner == p.github_owner and new_repo == p.github_repo:
                print("  (no change)")
                continue

            if new_url != p.github_url:
                clash = (await s.execute(
                    select(Project).where(Project.github_url == new_url, Project.id != p.id)
                )).scalar_one_or_none()
                if clash is not None:
                    print(f"  !! CONFLICT: project #{clash.id} already uses {new_url!r}. Skipping.")
                    continue

            if args.apply:
                p.github_url = new_url
                p.github_owner = new_owner
                p.github_repo = new_repo
            changed += 1

        if args.apply and changed:
            await s.commit()
            print(f"\nApplied to {changed} project(s).")
        elif changed:
            print(f"\nDry-run — {changed} project(s) would change. Re-run with --apply to commit.")
        else:
            print("\nNothing to change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""Reset findings + artifacts to a clean state.

Use case: stale data from prior CI runs polluting the dashboard
(e.g. Trivy container CVEs from old runs after retention bump on
SAST artifacts). Wipes findings and artifacts but keeps Projects so
you don't lose GitHub repo wiring.

Safe by default: dry-run unless --apply is passed.

Usage:
    python -m scripts.reset_db            # dry-run
    python -m scripts.reset_db --apply    # actually wipe
    python -m scripts.reset_db --apply --keep-processed  # only wipe failed/pending
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import delete, func, select

from src.core.db import AsyncSessionLocal
from src.models.entities import Artifact, Finding, Project


async def report() -> None:
    async with AsyncSessionLocal() as s:
        proj = (await s.execute(select(func.count(Project.id)))).scalar()
        art = (await s.execute(select(func.count(Artifact.id)))).scalar()
        find = (await s.execute(select(func.count(Finding.id)))).scalar()
        print(f"  projects:  {proj}")
        print(f"  artifacts: {art}")
        print(f"  findings:  {find}")


async def reset(apply: bool, keep_processed: bool) -> None:
    async with AsyncSessionLocal() as s:
        if keep_processed:
            ids = (await s.execute(
                select(Artifact.id).where(Artifact.status != "processed")
            )).scalars().all()
            print(f"\nWill delete {len(ids)} non-processed artifacts and their findings.")
        else:
            ids = (await s.execute(select(Artifact.id))).scalars().all()
            print(f"\nWill delete ALL {len(ids)} artifacts and their findings.")

        if not ids:
            print("Nothing to delete.")
            return

        if not apply:
            print("(Dry-run — pass --apply to actually delete)")
            return

        await s.execute(delete(Finding).where(Finding.artifact_id.in_(ids)))
        await s.execute(delete(Artifact).where(Artifact.id.in_(ids)))
        await s.commit()
        print("Done.")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--keep-processed", action="store_true",
                    help="Only delete failed/pending artifacts (preserve processed data)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING)
    print("=== Before ===")
    await report()
    await reset(apply=args.apply, keep_processed=args.keep_processed)
    if args.apply:
        print("\n=== After ===")
        await report()


if __name__ == "__main__":
    asyncio.run(main())

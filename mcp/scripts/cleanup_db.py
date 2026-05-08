"""Cleanup orphan failed artifacts and their findings.

Use case: GitHub Actions deleted SAST artifacts (retention-days=1) before
the poller could fetch them. Those artifacts sit in the DB with status='failed'
and 0 findings, polluting the artifact count UI shown on Pipelines.

This script:
  1. Counts artifacts grouped by status.
  2. Deletes Artifact rows where status='failed' AND no findings linked.
  3. Cascade-deletes findings of failed artifacts that DO have findings
     (rare — would only happen if a partial parse succeeded then failed).

Safe by default: dry-run unless --apply is passed.

Usage:
    python -m scripts.cleanup_db            # dry-run
    python -m scripts.cleanup_db --apply    # actually delete
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import delete, func, select

from src.core.db import AsyncSessionLocal
from src.models.entities import Artifact, Finding


async def report() -> None:
    async with AsyncSessionLocal() as s:
        total_a = (await s.execute(select(func.count(Artifact.id)))).scalar()
        total_f = (await s.execute(select(func.count(Finding.id)))).scalar()
        rows = (await s.execute(
            select(Artifact.status, func.count(Artifact.id)).group_by(Artifact.status)
        )).all()
        print(f"Total artifacts: {total_a}")
        print(f"Total findings:  {total_f}")
        print("By status:")
        for status, cnt in rows:
            print(f"  {status:12s} {cnt}")


async def cleanup(apply: bool) -> None:
    async with AsyncSessionLocal() as s:
        # Find failed artifacts
        failed = (await s.execute(
            select(Artifact.id).where(Artifact.status == "failed")
        )).scalars().all()
        if not failed:
            print("No failed artifacts found — nothing to clean.")
            return

        # Findings linked to failed artifacts (should be 0 for proper failures)
        orphan_findings = (await s.execute(
            select(func.count(Finding.id)).where(Finding.artifact_id.in_(failed))
        )).scalar()

        print(f"Failed artifacts:        {len(failed)}")
        print(f"Findings to also delete: {orphan_findings}")

        if not apply:
            print("\n(Dry-run — pass --apply to actually delete)")
            return

        await s.execute(delete(Finding).where(Finding.artifact_id.in_(failed)))
        await s.execute(delete(Artifact).where(Artifact.id.in_(failed)))
        await s.commit()
        print("Done.")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Actually delete (default: dry-run)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING)
    print("=== Before ===")
    await report()
    print("\n=== Cleanup plan ===")
    await cleanup(apply=args.apply)
    if args.apply:
        print("\n=== After ===")
        await report()


if __name__ == "__main__":
    asyncio.run(main())

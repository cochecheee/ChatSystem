"""V4.4 — backfill OWASP class + standard reference URLs onto existing findings.

Findings ingested before V4.4 have `owasp_class = NULL` and no `raw_data['references']`.
Re-running a full CI scan would populate them, but this script backfills in place
without waiting for CI: for every finding it re-runs the same `classify_owasp` +
`build_references` the enricher uses at ingest, then writes `owasp_class` (column)
and merges `owasp_category`/`owasp_class`/`references` into `raw_data`.

Safe by default: dry-run unless --apply is passed.

Usage:
    python -m scripts.backfill_owasp_class            # dry-run (show distribution)
    python -m scripts.backfill_owasp_class --apply    # write owasp_class + references
    python -m scripts.backfill_owasp_class --apply --project 14   # scope to one project
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections import Counter

from sqlalchemy import select

from src.core.db import AsyncSessionLocal
from src.models.entities import Finding
from src.models.schemas import FindingCreate
from src.services.enricher import build_references, classify_owasp, parse_cwe_number

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _as_create(f: Finding) -> FindingCreate:
    return FindingCreate(
        artifact_id=f.artifact_id,
        tool=f.tool,
        rule_id=f.rule_id,
        severity=f.severity,
        message=f.message,
        file_path=f.file_path,
        line_number=f.line_number,
        cwe_id=f.cwe_id,
        cvss_score=f.cvss_score,
        raw_data=f.raw_data,
    )


async def backfill(apply: bool, project_id: int | None) -> None:
    dist: Counter[str] = Counter()
    updated = 0
    async with AsyncSessionLocal() as s:
        query = select(Finding)
        if project_id is not None:
            query = query.where(Finding.project_id == project_id)
        findings = (await s.execute(query)).scalars().all()

        for f in findings:
            fc = _as_create(f)
            code, label = classify_owasp(fc)
            refs = build_references(fc, parse_cwe_number(f.cwe_id), code)
            dist[code] += 1

            if not apply:
                continue

            f.owasp_class = code
            new_raw = dict(f.raw_data or {})
            new_raw["owasp_category"] = label
            new_raw["owasp_class"] = code
            if refs:
                new_raw["references"] = refs
            f.raw_data = new_raw  # reassign so the JSON column is marked dirty
            updated += 1

        if apply:
            await s.commit()

    scope = f"project {project_id}" if project_id is not None else "all projects"
    print(f"=== OWASP class distribution ({scope}, {sum(dist.values())} findings) ===")
    for code, n in sorted(dist.items()):
        print(f"  {code}  {n}")
    if apply:
        print(f"\nBackfilled {updated} findings (owasp_class + references written).")
    else:
        print("\n(Dry-run — pass --apply to write owasp_class + references)")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    ap.add_argument("--project", type=int, default=None, help="Scope to one project id")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING)
    await backfill(apply=args.apply, project_id=args.project)


if __name__ == "__main__":
    asyncio.run(main())

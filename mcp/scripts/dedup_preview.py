#!/usr/bin/env python
"""dedup_preview — READ-ONLY. Rank projects by cross-tool dedup potential.

For each project's latest run, recompute the correlation clusters the same way
`SecurityProcessor._correlate_run_findings` does (category | file | CWE |
line-bucket), WITHOUT touching the DB. Use it to pick the best project to demo
the V4.0 cross-tool dedup: the one whose latest scan has the most multi-tool
clusters (same bug flagged by >= 2 different tools).

Run from mcp/ with the app venv:
    .venv/Scripts/python.exe scripts/dedup_preview.py
    .venv/Scripts/python.exe scripts/dedup_preview.py --project 2 --show 12
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from src.core.db import AsyncSessionLocal  # noqa: E402
from src.models.entities import Artifact, Finding, Project  # noqa: E402
from src.repositories.finding_repo import DAST_TOOLS, DEPS_TOOLS  # noqa: E402

WINDOW = max(1, int(os.getenv("DEDUP_LINE_WINDOW", "5") or 5))


def _category(tool: str) -> str:
    t = (tool or "").lower()
    if t in DEPS_TOOLS:
        return "deps"
    if t in DAST_TOOLS:
        return "dast"
    return "sast"


def _norm_path(p: str | None) -> str:
    s = (p or "").strip().replace("\\", "/").lower()
    while s.startswith("./"):
        s = s[2:]
    return s


def _cwe_num(cwe_id: str | None):
    if not cwe_id:
        return None
    d = cwe_id.upper().replace("CWE-", "").strip()
    return int(d) if d.isdigit() else None


def _key(f: Finding) -> str | None:
    cwe = _cwe_num(f.cwe_id)
    if cwe is None:
        return None
    bucket = str(f.line_number // WINDOW) if f.line_number is not None else "na"
    return f"{_category(f.tool)}|{_norm_path(f.file_path)}|CWE-{cwe}|{bucket}"


async def _latest_run(session, pid: int):
    return (await session.execute(
        select(func.max(Artifact.github_run_id))
        .join(Finding, Finding.artifact_id == Artifact.id)
        .where(Artifact.project_id == pid, Artifact.github_run_id.is_not(None))
    )).scalar_one_or_none()


async def _findings(session, pid: int, run: int):
    art_ids = [r[0] for r in (await session.execute(
        select(Artifact.id).where(Artifact.project_id == pid, Artifact.github_run_id == run)
    )).all()]
    if not art_ids:
        return []
    return list((await session.execute(
        select(Finding).where(Finding.artifact_id.in_(art_ids))
    )).scalars().all())


def _analyze(findings):
    groups: dict[str, list[Finding]] = defaultdict(list)
    already = 0
    for f in findings:
        if isinstance(f.raw_data, dict) and f.raw_data.get("_correlation"):
            already += 1
        k = _key(f)
        if k:
            groups[k].append(f)
    clusters = {k: v for k, v in groups.items() if len(v) >= 2}
    multi_tool = {
        k: v for k, v in clusters.items()
        if len({(x.tool or "").lower() for x in v}) >= 2
    }
    removable = sum(len(v) - 1 for v in clusters.values())
    return {
        "total": len(findings),
        "clusters": clusters,
        "multi_tool": multi_tool,
        "removable": removable,
        "already": already,
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=int, default=None)
    ap.add_argument("--show", type=int, default=6, help="example clusters to print for top project")
    ap.add_argument("--min-tools", type=int, default=2)
    args = ap.parse_args()

    async with AsyncSessionLocal() as s:
        projects = (await s.execute(select(Project).order_by(Project.id))).scalars().all()
        if args.project is not None:
            projects = [p for p in projects if p.id == args.project]

        rows = []
        detail = {}
        for p in projects:
            run = await _latest_run(s, p.id)
            if run is None:
                continue
            a = _analyze(await _findings(s, p.id, run))
            rows.append((p, run, a))
            detail[p.id] = a

    if not rows:
        print("No projects with findings.")
        return 0

    rows.sort(key=lambda r: (len(r[2]["multi_tool"]), r[2]["removable"]), reverse=True)

    print(f"\n{'id':>3}  {'project':<22} {'run':>10}  {'find':>5}  {'m-tool':>6}  {'remov':>5}  note")
    print("-" * 78)
    for p, run, a in rows:
        note = "ALREADY deduped" if a["already"] else ""
        print(f"{p.id:>3}  {p.name[:22]:<22} {str(run):>10}  {a['total']:>5}  "
              f"{len(a['multi_tool']):>6}  {a['removable']:>5}  {note}")

    # Recommend + show examples for the best candidate.
    best = next((r for r in rows if r[2]["multi_tool"] and not r[2]["already"]), None)
    if best is None:
        best = rows[0]
    p, run, a = best
    print(f"\n>>> Best demo candidate: project #{p.id} ({p.name}), run {run} — "
          f"{len(a['multi_tool'])} multi-tool cluster(s), {a['removable']} removable duplicate(s).")
    if a["already"]:
        print("    (this run was already correlated — use `dedup_viz --project %d`)" % p.id)

    shown = sorted(a["multi_tool"].values(), key=lambda v: len(v), reverse=True)[: args.show]
    for members in shown:
        f0 = members[0]
        tools = sorted({m.tool for m in members})
        loc = f"{f0.file_path}:{f0.line_number if f0.line_number is not None else '-'}"
        print(f"\n  * {f0.cwe_id or '-':<8} {loc}   x{len(members)}  [{', '.join(tools)}]")
        for m in members:
            print(f"      - {m.tool:<10} {m.severity:<8} {m.rule_id}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

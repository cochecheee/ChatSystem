#!/usr/bin/env python
"""dedup_scenario — import a BRAND-NEW project from a real run's raw findings,
then show BEFORE -> DEDUP -> AFTER with a full diff.

Seeds a fresh project (unique github_url) with the RAW (pre-dedup) findings of a
source run — reconstructing the raw set from each keeper's
raw_data._correlation.members so the "before" is authentic real data, not
synthetic. Then runs the real exact-dedup + cross-tool correlation and prints a
before/after comparison + diff. Writes before.json / after.json / diff.json.

Idempotent: re-running deletes the previous scenario project of the same URL.
Use --keep to leave the project in the DB (e.g. to open it on the dashboard).

Run from mcp/ with the app venv:
    .venv/Scripts/python.exe scripts/dedup_scenario.py --source 10
    .venv/Scripts/python.exe scripts/dedup_scenario.py --source 10 --name pygoat-dedup-scenario --keep
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select  # noqa: E402

from src.core.db import AsyncSessionLocal  # noqa: E402
from src.models.entities import (  # noqa: E402
    Artifact, CommandFeedback, Finding, FindingAction, Project,
)
from src.models.schemas import compute_dedup_hash  # noqa: E402
from src.services.processor import SecurityProcessor  # noqa: E402

SEV_ORDER = ["critical", "high", "medium", "low", "info"]


async def _latest_run(s, pid):
    return (await s.execute(
        select(func.max(Artifact.github_run_id))
        .join(Finding, Finding.artifact_id == Artifact.id)
        .where(Artifact.project_id == pid, Artifact.github_run_id.is_not(None))
    )).scalar_one_or_none()


async def gather_raw(s, source_pid):
    """Reconstruct the pre-dedup finding set of the source project's latest run."""
    run = await _latest_run(s, source_pid)
    if run is None:
        return None, []
    art_ids = [r[0] for r in (await s.execute(
        select(Artifact.id).where(Artifact.project_id == source_pid, Artifact.github_run_id == run)
    )).all()]
    findings = list((await s.execute(
        select(Finding).where(Finding.artifact_id.in_(art_ids))
    )).scalars().all())

    raw = []
    for f in findings:
        rd = dict(f.raw_data) if isinstance(f.raw_data, dict) else {}
        corr = rd.pop("_correlation", None)  # strip so the new project starts RAW
        raw.append({
            "tool": f.tool, "rule_id": f.rule_id, "severity": f.severity,
            "cwe_id": f.cwe_id, "file_path": f.file_path, "line_number": f.line_number,
            "message": f.message, "cvss_score": f.cvss_score, "raw_data": rd,
        })
        for m in (corr or {}).get("members", []):
            raw.append({
                "tool": m.get("tool"), "rule_id": m.get("rule_id"),
                "severity": m.get("severity"), "cwe_id": f.cwe_id,
                "file_path": f.file_path, "line_number": m.get("line_number"),
                "message": m.get("message", ""), "cvss_score": None, "raw_data": {},
            })
    return run, raw


async def delete_project_by_url(s, url):
    proj = (await s.execute(select(Project).where(Project.github_url == url))).scalar_one_or_none()
    if proj is None:
        return
    fids = [r[0] for r in (await s.execute(
        select(Finding.id).where(Finding.project_id == proj.id)
    )).all()]
    if fids:
        await s.execute(delete(FindingAction).where(FindingAction.finding_id.in_(fids)))
        await s.execute(delete(CommandFeedback).where(CommandFeedback.finding_id.in_(fids)))
    await s.execute(delete(Finding).where(Finding.project_id == proj.id))
    await s.execute(delete(Artifact).where(Artifact.project_id == proj.id))
    await s.execute(delete(Project).where(Project.id == proj.id))
    await s.commit()


async def snapshot(s, pid):
    total = (await s.execute(
        select(func.count(Finding.id)).where(Finding.project_id == pid)
    )).scalar_one()
    by_tool = {t: n for t, n in (await s.execute(
        select(Finding.tool, func.count(Finding.id)).where(Finding.project_id == pid).group_by(Finding.tool)
    )).all()}
    by_sev = {sv: n for sv, n in (await s.execute(
        select(Finding.severity, func.count(Finding.id)).where(Finding.project_id == pid).group_by(Finding.severity)
    )).all()}
    # gate-active counts (exclude REVOKED/APPROVED) — all pending here, so == raw counts
    gate = {}
    for sev in ("critical", "high"):
        gate[sev] = (await s.execute(
            select(func.count(Finding.id)).where(
                Finding.project_id == pid, Finding.severity == sev,
                Finding.status != "REVOKED", Finding.status != "APPROVED",
            )
        )).scalar_one()
    return {"total": total, "by_tool": by_tool, "by_severity": by_sev, "gate": gate}


async def clusters(s, pid):
    rows = list((await s.execute(
        select(Finding).where(Finding.project_id == pid)
    )).scalars().all())
    out = []
    for f in rows:
        corr = (f.raw_data or {}).get("_correlation") if isinstance(f.raw_data, dict) else None
        if corr and corr.get("size", 1) >= 2:
            out.append({
                "finding_id": f.id, "cwe": corr.get("cwe"), "severity": corr.get("severity_max"),
                "file": f.file_path, "line": f.line_number, "size": corr["size"],
                "tools": corr.get("tools"), "primary": corr.get("primary_tool"),
            })
    out.sort(key=lambda c: c["size"], reverse=True)
    return out


def _fmt_counts(d):
    return "  ".join(f"{k}={d.get(k, 0)}" for k in SEV_ORDER if d.get(k)) or "-"


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=int, default=10, help="source project id (data seed)")
    ap.add_argument("--name", default="dedup-scenario")
    ap.add_argument("--keep", action="store_true", help="leave the scenario project in the DB")
    ap.add_argument("--out", default=None, help="dir to write before/after/diff json")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    url = f"https://github.com/dedup-demo/{args.name}"
    run = None

    async with AsyncSessionLocal() as s:
        src = await s.get(Project, args.source)
        if src is None:
            print(f"source project {args.source} not found")
            return 1
        src_name = src.name
        run, raw = await gather_raw(s, args.source)
        if not raw:
            print("source has no findings")
            return 1

        # reset + create fresh project
        await delete_project_by_url(s, url)
        proj = Project(
            name=args.name, github_url=url,
            github_owner="dedup-demo", github_repo=args.name,
            active=0, last_processed_run_id=10**12,  # inactive → poller ignores
        )
        s.add(proj)
        await s.commit()
        await s.refresh(proj)
        pid = proj.id

        # seed RAW findings under one synthetic run/artifact
        art = Artifact(
            github_artifact_id="scenario", project_id=pid,
            github_run_id=run, status="processed",
        )
        s.add(art)
        await s.commit()
        await s.refresh(art)
        now = datetime.now(UTC)
        for r in raw:
            s.add(Finding(
                artifact_id=art.id, project_id=pid, tool=r["tool"], rule_id=r["rule_id"],
                severity=r["severity"], message=r["message"], file_path=r["file_path"],
                line_number=r["line_number"], cwe_id=r["cwe_id"], cvss_score=r["cvss_score"],
                raw_data=r["raw_data"], status="pending_review", normalized_at=now,
                dedup_hash=compute_dedup_hash(r["rule_id"], r["file_path"], r["message"]),
            ))
        await s.commit()

        before = await snapshot(s, pid)

    print(f"\n=== DEDUP SCENARIO — new project '{args.name}' (id={pid}) ===")
    print(f"    seeded from project #{args.source} ({src_name}), run {run} — RAW findings\n")
    print(f"[1] BEFORE dedup: {before['total']} findings")
    print(f"    by tool    : " + "  ".join(f"{t}={n}" for t, n in sorted(before['by_tool'].items(), key=lambda kv: -kv[1])))
    print(f"    by severity: {_fmt_counts(before['by_severity'])}")
    print(f"    gate-active: critical={before['gate']['critical']}  high={before['gate']['high']}")

    # DEDUP
    proc = SecurityProcessor()
    exact = await proc._dedup_run_findings(pid, run)
    cross = await proc._correlate_run_findings(pid, run)
    print(f"\n[2] DEDUP: exact-hash removed {exact}, cross-tool removed {cross}")

    async with AsyncSessionLocal() as s:
        after = await snapshot(s, pid)
        cls = await clusters(s, pid)

    print(f"\n[3] AFTER dedup: {after['total']} findings")
    print(f"    by tool    : " + "  ".join(f"{t}={n}" for t, n in sorted(after['by_tool'].items(), key=lambda kv: -kv[1])))
    print(f"    by severity: {_fmt_counts(after['by_severity'])}")
    print(f"    gate-active: critical={after['gate']['critical']}  high={after['gate']['high']}")

    removed = before["total"] - after["total"]
    pct = round(100 * removed / before["total"], 1) if before["total"] else 0
    multi = [c for c in cls if len(c["tools"] or []) >= 2]
    print(f"\n[DIFF] removed {removed} duplicate findings ({pct}% reduction) — "
          f"{len(cls)} merged cluster(s), {len(multi)} of them cross-tool (>=2 tools)")
    print(f"    gate crit: {before['gate']['critical']} -> {after['gate']['critical']}   "
          f"gate high: {before['gate']['high']} -> {after['gate']['high']}")
    for c in cls[:10]:
        kind = "cross-tool" if len(c["tools"] or []) >= 2 else "same-tool"
        print(f"    * {c['cwe']:<8} {c['severity']:<8} {c['file']}:{c['line']}  "
              f"x{c['size']} [{', '.join(c['tools'])}] ({kind})")

    diff = {
        "source_project": args.source, "source_name": src_name, "run": run,
        "scenario_project_id": pid, "scenario_url": url,
        "before": before, "after": after,
        "removed": removed, "reduction_pct": pct,
        "exact_removed": exact, "cross_tool_removed": cross,
        "merged_clusters": len(cls), "cross_tool_clusters": len(multi),
        "clusters": cls,
    }
    if args.out:
        d = Path(args.out)
        d.mkdir(parents=True, exist_ok=True)
        (d / "before.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
        (d / "after.json").write_text(json.dumps(after, indent=2), encoding="utf-8")
        (d / "diff.json").write_text(json.dumps(diff, indent=2), encoding="utf-8")
        print(f"\n    wrote before/after/diff json to {d}")

    if not args.keep:
        async with AsyncSessionLocal() as s:
            await delete_project_by_url(s, url)
        print(f"\n    (scenario project deleted — pass --keep to retain it)")
    else:
        print(f"\n    (scenario project KEPT: id={pid}, name='{args.name}' — visible on dashboard)")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

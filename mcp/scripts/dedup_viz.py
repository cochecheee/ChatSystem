#!/usr/bin/env python
"""dedup_viz — terminal visualization of cross-tool deduplication (V4.0).

Read-only. Reconstructs the cross-tool dedup funnel + the corroborated clusters
for a project's latest run (or a specific --run) from the canonical findings'
`raw_data['_correlation']` records that `SecurityProcessor._correlate_run_findings`
writes at ingest. Never mutates the database.

Usage (run from the `mcp/` directory):

    python -m scripts.dedup_viz --list                 # list projects
    python -m scripts.dedup_viz --project 1             # latest run of project 1
    python -m scripts.dedup_viz --project 1 --run 478   # a specific GitHub run
    python -m scripts.dedup_viz --project 1 --min-size 3 --no-color --ascii

Reads DATABASE_URL from the app settings (.env), so it points at the same DB
the backend uses (local MySQL in dev — see memory `mysql-datetime-gotcha`).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow both `python -m scripts.dedup_viz` and `python scripts/dedup_viz.py`
# by putting the mcp/ dir (parent of scripts/) on sys.path so `src` imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from src.core.db import AsyncSessionLocal  # noqa: E402
from src.models.entities import Artifact, Finding, Project  # noqa: E402

# --------------------------------------------------------------------------
# Output setup — ANSI color + unicode/ascii glyphs (dependency-free; `rich`
# is not installed, and the Windows console defaults to cp1252 which cannot
# encode block/box-drawing chars → we reconfigure to UTF-8 and fall back to
# ASCII glyphs when the stream still can't handle unicode).
# --------------------------------------------------------------------------

_ENABLE_COLOR = True

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
GREY = "\033[38;5;245m"
GREEN = "\033[38;5;35m"
ORANGE = "\033[38;5;208m"

_SEV_COLOR = {
    "critical": "\033[38;5;196m",
    "high": "\033[38;5;208m",
    "medium": "\033[38;5;220m",
    "low": "\033[38;5;39m",
    "info": "\033[38;5;245m",
}
_SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}

_G_UNICODE = {"full": "█", "empty": "░", "bullet": "●", "tee": "├─", "elbow": "└─", "arrow": "←"}
_G_ASCII = {"full": "#", "empty": "-", "bullet": "*", "tee": "|-", "elbow": "`-", "arrow": "<-"}
GLYPH = dict(_G_UNICODE)


def _setup_output(no_color: bool, force_ascii: bool) -> None:
    global _ENABLE_COLOR, GLYPH
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    enc = (getattr(sys.stdout, "encoding", None) or "").lower()
    unicode_ok = "utf" in enc
    if force_ascii or not unicode_ok:
        GLYPH = dict(_G_ASCII)
    _ENABLE_COLOR = (not no_color) and sys.stdout.isatty()


def _c(code: str) -> str:
    return code if _ENABLE_COLOR else ""


def sev_tag(sev: str | None) -> str:
    s = (sev or "info").lower()
    return f"{_c(_SEV_COLOR.get(s, ''))}{s.upper().ljust(8)}{_c(RESET)}"


def bar(value: int, total: int, width: int = 34, color: str = "") -> str:
    filled = round(width * value / total) if total > 0 else 0
    filled = max(0, min(width, filled))
    return (f"{_c(color)}{GLYPH['full'] * filled}"
            f"{_c(DIM)}{GLYPH['empty'] * (width - filled)}{_c(RESET)}")


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

async def _list_projects() -> None:
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(
            select(Project.id, Project.name, Project.github_url).order_by(Project.id)
        )).all()
    if not rows:
        print("(no projects)")
        return
    print(f"{_c(BOLD)}Projects{_c(RESET)}")
    for pid, name, url in rows:
        print(f"  {_c(BOLD)}{pid:>3}{_c(RESET)}  {name}  {_c(DIM)}{url or ''}{_c(RESET)}")
    print("\nRun again with --project <id> to see its dedup funnel.")


async def _load(project_id: int, run_id: int | None):
    async with AsyncSessionLocal() as s:
        proj = await s.get(Project, project_id)
        if proj is None:
            return None, None, []
        if run_id is None:
            run_id = (await s.execute(
                select(func.max(Artifact.github_run_id))
                .join(Finding, Finding.artifact_id == Artifact.id)
                .where(
                    Artifact.project_id == project_id,
                    Artifact.github_run_id.is_not(None),
                )
            )).scalar_one_or_none()
        if run_id is None:
            return proj, None, []
        art_ids = [r[0] for r in (await s.execute(
            select(Artifact.id).where(
                Artifact.project_id == project_id,
                Artifact.github_run_id == run_id,
            )
        )).all()]
        if not art_ids:
            return proj, run_id, []
        findings = (await s.execute(
            select(Finding).where(Finding.artifact_id.in_(art_ids))
        )).scalars().all()
        return proj, run_id, list(findings)


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------

def _render(proj: Project, run_id, findings: list[Finding], min_size: int) -> None:
    unique = len(findings)
    removed = 0
    clusters: list[dict] = []
    by_tool: dict[str, int] = {}

    for f in findings:
        raw = f.raw_data if isinstance(f.raw_data, dict) else {}
        corr = raw.get("_correlation")
        if not corr:
            continue
        size = int(corr.get("size", 1) or 1)
        if size < 2:
            continue
        removed += size - 1
        for t in (corr.get("tools") or []):
            by_tool[t] = by_tool.get(t, 0) + 1
        clusters.append({
            "finding": f, "corr": corr, "size": size,
            "sev": corr.get("severity_max") or f.severity,
        })

    raw_est = unique + removed
    pct = (100.0 * removed / raw_est) if raw_est else 0.0
    multi = sum(1 for c in clusters if len(c["corr"].get("tools") or []) >= 2)

    print()
    print(f"{_c(BOLD)}=== Cross-tool deduplication ==={_c(RESET)}")
    print(f"  project  {_c(BOLD)}{proj.name}{_c(RESET)}  (id={proj.id})   run {_c(BOLD)}{run_id}{_c(RESET)}")
    print()

    # Funnel
    print(f"  {'Raw (pre cross-tool)':<24}{bar(raw_est, raw_est, color=GREY)} {_c(BOLD)}{raw_est}{_c(RESET)}")
    print(f"  {'Unique (deduped)':<24}{bar(unique, raw_est, color=GREEN)} {_c(BOLD)}{unique}{_c(RESET)}")
    print(f"  {'Duplicates removed':<24}{bar(removed, raw_est, color=ORANGE)} {_c(BOLD)}{removed}{_c(RESET)}"
          f"  {_c(DIM)}({pct:.1f}% reduction){_c(RESET)}")
    print()
    print(f"  merged clusters: {_c(BOLD)}{len(clusters)}{_c(RESET)}"
          f"   -   multi-tool clusters: {_c(BOLD)}{multi}{_c(RESET)}")
    if by_tool:
        contrib = "  ".join(f"{t} x{n}" for t, n in sorted(by_tool.items(), key=lambda kv: -kv[1]))
        print(f"  {_c(DIM)}tool participation:{_c(RESET)} {contrib}")

    # Clusters
    shown = [c for c in clusters if c["size"] >= min_size]
    shown.sort(key=lambda c: (_SEV_RANK.get((c["sev"] or "").lower(), 0), c["size"]), reverse=True)
    print()
    if not shown:
        print(f"  {_c(DIM)}(no clusters with size >= {min_size} — run may predate V4.0 correlation){_c(RESET)}")
        print()
        return

    print(f"{_c(BOLD)}  Corroborated clusters (size >= {min_size}){_c(RESET)}")
    for c in shown:
        f = c["finding"]
        corr = c["corr"]
        cwe = corr.get("cwe") or f.cwe_id or "-"
        loc = f"{f.file_path}:{f.line_number if f.line_number is not None else '-'}"
        print(f"\n  {GLYPH['bullet']} {sev_tag(c['sev'])} {_c(BOLD)}{cwe:<9}{_c(RESET)} {loc}"
              f"   {_c(DIM)}x{c['size']} findings{_c(RESET)}")
        entries = [(f.tool, f.rule_id, True)]
        for m in (corr.get("members") or []):
            entries.append((m.get("tool"), m.get("rule_id"), False))
        for i, (tool, rule, is_primary) in enumerate(entries):
            branch = GLYPH["elbow"] if i == len(entries) - 1 else GLYPH["tee"]
            tag = f" {_c(GREEN)}{GLYPH['arrow']} primary{_c(RESET)}" if is_primary else ""
            print(f"      {branch} {str(tool or '?'):<10} {_c(DIM)}{rule or ''}{_c(RESET)}{tag}")
    print()


async def _main() -> int:
    ap = argparse.ArgumentParser(description="Visualize cross-tool dedup for a run.")
    ap.add_argument("--project", type=int, help="project id")
    ap.add_argument("--run", type=int, default=None, help="GitHub run id (default: latest)")
    ap.add_argument("--min-size", type=int, default=2, help="min cluster size to show")
    ap.add_argument("--list", action="store_true", help="list projects and exit")
    ap.add_argument("--no-color", action="store_true", help="disable ANSI color")
    ap.add_argument("--ascii", action="store_true", help="force ASCII glyphs")
    args = ap.parse_args()

    _setup_output(no_color=args.no_color, force_ascii=args.ascii)

    if args.list or args.project is None:
        await _list_projects()
        return 0

    proj, run_id, findings = await _load(args.project, args.run)
    if proj is None:
        print(f"project {args.project} not found")
        return 1
    if run_id is None:
        print(f"project {proj.name} (id={proj.id}) has no runs with findings yet")
        return 0
    _render(proj, run_id, findings, args.min_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))

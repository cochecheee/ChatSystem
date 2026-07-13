#!/usr/bin/env python
"""dedup_demo — narrated BEFORE -> APPLY -> AFTER demo of cross-tool dedup.

READ-ONLY and repeatable. Uses the data of ONE run. Prints three clearly
timestamped phases:

  [T0] BEFORE  — the raw findings as every tool reported them (duplicates shown)
  [T1] APPLY   — run the exact correlation algorithm (in memory, no DB writes)
  [T2] AFTER   — the deduped result + the cross-tool clusters + the funnel

Works whether or not the run has already been correlated: if it has, the raw
"before" set is reconstructed from each keeper's raw_data._correlation.members
(the dropped duplicates are preserved there), so the demo never mutates the DB
and can be replayed any number of times.

Run from mcp/ with the app venv:
    .venv/Scripts/python.exe scripts/dedup_demo.py --project 10
    .venv/Scripts/python.exe scripts/dedup_demo.py --project 10 --pause   # wait <Enter> between phases
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from src.core.db import AsyncSessionLocal  # noqa: E402
from src.models.entities import Artifact, Finding, Project  # noqa: E402
from src.repositories.finding_repo import DAST_TOOLS, DEPS_TOOLS  # noqa: E402

WINDOW = max(1, int(os.getenv("DEDUP_LINE_WINDOW", "5") or 5))

_SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
_STATUS_PRIORITY = {"REVOKED": 3, "APPROVED": 3, "ai_analyzed": 2}
_TOOL_PRIORITY = {
    "codeql": 6, "semgrep": 5, "semgrep oss": 5,
    "spotbugs": 4, "bandit": 4, "gosec": 4, "eslint": 3,
    "npm-audit": 2, "safety": 2, "dependency-check": 2, "trivy": 1,
}

_COLOR = True
def c(code: str) -> str:  # noqa: E302
    return code if _COLOR else ""
R, B, D = "\033[0m", "\033[1m", "\033[2m"
CY, GR, OR = "\033[38;5;39m", "\033[38;5;35m", "\033[38;5;208m"


def _category(tool: str) -> str:
    t = (tool or "").lower()
    if t in DEPS_TOOLS:
        return "deps"
    if t in DAST_TOOLS:
        return "dast"
    return "sast"


def _cwe_num(cwe_id):
    if not cwe_id:
        return None
    d = str(cwe_id).upper().replace("CWE-", "").strip()
    return int(d) if d.isdigit() else None


def _key(rec: dict):
    cwe = _cwe_num(rec["cwe_id"])
    if cwe is None:
        return None
    path = (rec["file_path"] or "").strip().replace("\\", "/").lower()
    while path.startswith("./"):
        path = path[2:]
    ln = rec["line_number"]
    bucket = str(ln // WINDOW) if ln is not None else "na"
    return f"{_category(rec['tool'])}|{path}|CWE-{cwe}|{bucket}"


def _stamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _reconstruct_raw(findings) -> list[dict]:
    """Rebuild the pre-dedup finding set. Every stored row is a keeper/singleton;
    correlated keepers carry their dropped duplicates under _correlation.members
    (members inherit the keeper's file_path + CWE, keep their own tool/line)."""
    raw: list[dict] = []
    for f in findings:
        rd = f.raw_data if isinstance(f.raw_data, dict) else {}
        raw.append({
            "tool": f.tool, "rule_id": f.rule_id, "severity": f.severity,
            "cwe_id": f.cwe_id, "file_path": f.file_path, "line_number": f.line_number,
            "status": f.status, "has_ai": 1 if f.ai_analysis is not None else 0,
        })
        corr = rd.get("_correlation") or {}
        for m in corr.get("members", []):
            raw.append({
                "tool": m.get("tool"), "rule_id": m.get("rule_id"),
                "severity": m.get("severity"), "cwe_id": f.cwe_id,
                "file_path": f.file_path, "line_number": m.get("line_number"),
                "status": "pending_review", "has_ai": 0,
            })
    return raw


def _cluster(raw: list[dict]):
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in raw:
        k = _key(r)
        if k:
            groups[k].append(r)
    merged = {k: v for k, v in groups.items() if len(v) >= 2}
    kept = len(raw) - sum(len(v) - 1 for v in merged.values())
    return groups, merged, kept


def _tools_of(members):
    return sorted({(m["tool"] or "").lower() for m in members})


async def _load(pid, run):
    async with AsyncSessionLocal() as s:
        proj = await s.get(Project, pid)
        if proj is None:
            return None, None, []
        if run is None:
            run = (await s.execute(
                select(func.max(Artifact.github_run_id))
                .join(Finding, Finding.artifact_id == Artifact.id)
                .where(Artifact.project_id == pid, Artifact.github_run_id.is_not(None))
            )).scalar_one_or_none()
        if run is None:
            return proj, None, []
        art_ids = [r[0] for r in (await s.execute(
            select(Artifact.id).where(Artifact.project_id == pid, Artifact.github_run_id == run)
        )).all()]
        findings = list((await s.execute(
            select(Finding).where(Finding.artifact_id.in_(art_ids))
        )).scalars().all()) if art_ids else []
        return proj, run, findings


def _hr():
    print(c(D) + "-" * 70 + c(R))


async def main() -> int:
    global _COLOR
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=int, required=True)
    ap.add_argument("--run", type=int, default=None)
    ap.add_argument("--pause", action="store_true", help="wait for <Enter> between phases")
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument("--show", type=int, default=6)
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    _COLOR = (not args.no_color) and sys.stdout.isatty()

    proj, run, findings = await _load(args.project, args.run)
    if proj is None:
        print("project not found"); return 1
    if not findings:
        print("no findings for this run"); return 0

    raw = _reconstruct_raw(findings)
    by_tool = defaultdict(int)
    for r in raw:
        by_tool[r["tool"]] += 1

    async def wait():
        if args.pause:
            try:
                input(c(D) + "    <Enter> để tiếp tục..." + c(R))
            except EOFError:
                pass
        else:
            await asyncio.sleep(0.7)  # visible gap so the 3 timestamps differ

    # ---- T0 BEFORE ----
    print()
    print(f"{c(B)}{c(CY)}[T0  {_stamp()}]  BEFORE{c(R)}  — dữ liệu thô 1 run: "
          f"project #{proj.id} {proj.name}, run {run}")
    _hr()
    print(f"  Tổng finding thô (mọi tool báo): {c(B)}{len(raw)}{c(R)}")
    print("  Theo tool: " + "  ".join(f"{t} {n}" for t, n in sorted(by_tool.items(), key=lambda kv: -kv[1])))
    _, merged_preview, _ = _cluster(raw)
    print(f"  → phát hiện {c(B)}{len(merged_preview)}{c(R)} cụm trùng "
          f"({c(B)}{sum(len(v) - 1 for v in merged_preview.values())}{c(R)} dòng là bản trùng của cùng 1 lỗi)")
    # show one concrete duplicated cluster in raw form
    example = max(merged_preview.values(), key=len, default=None)
    if example:
        e0 = example[0]
        print(f"\n  Ví dụ 1 lỗi bị báo trùng — {e0['cwe_id']} {e0['file_path']}:{e0['line_number']}")
        for m in example:
            print(f"      {c(D)}·{c(R)} {m['tool']:<12} {m['severity']:<8} {m['rule_id']}")
    print()
    await wait()

    # ---- T1 APPLY ----
    print(f"{c(B)}{c(OR)}[T1  {_stamp()}]  APPLY{c(R)}  — chạy correlation "
          f"(key = category | file | CWE | dòng//{WINDOW})")
    _hr()
    groups, merged, kept = _cluster(raw)
    removed = len(raw) - kept
    keepers = []
    for k, members in merged.items():
        keeper = max(members, key=lambda m: (
            _STATUS_PRIORITY.get(m["status"], 1),
            _SEV_RANK.get((m["severity"] or "").lower(), 0),
            m["has_ai"],
            _TOOL_PRIORITY.get((m["tool"] or "").lower(), 1),
        ))
        keepers.append((k, keeper, members))
    multi = [(k, kp, mem) for k, kp, mem in keepers if len(_tools_of(mem)) >= 2]
    print(f"  Gộp {c(B)}{len(merged)}{c(R)} cụm → xoá {c(B)}{removed}{c(R)} bản trùng, "
          f"giữ 1 canonical/cụm; ghi tool xác nhận vào keeper._correlation")
    print()
    await wait()

    # ---- T2 AFTER ----
    print(f"{c(B)}{c(GR)}[T2  {_stamp()}]  AFTER{c(R)}  — sau khi gộp")
    _hr()
    width = 40
    def bar(v, tot, col):
        fill = round(width * v / tot) if tot else 0
        return c(col) + "#" * fill + c(D) + "-" * (width - fill) + c(R)
    print(f"  Raw   {bar(len(raw), len(raw), OR)} {c(B)}{len(raw)}{c(R)}")
    print(f"  Unique{bar(kept, len(raw), GR)} {c(B)}{kept}{c(R)}"
          f"   {c(D)}(−{removed}, {round(100 * removed / len(raw), 1)}%){c(R)}")
    print(f"  {c(B)}{len(multi)}{c(R)} lỗi được ≥2 tool cùng xác nhận (độ tin cậy cao)")
    print()
    for k, keeper, members in sorted(multi, key=lambda x: _SEV_RANK.get((x[1]['severity'] or '').lower(), 0), reverse=True)[: args.show]:
        tools = _tools_of(members)
        print(f"  {c(B)}{keeper['cwe_id']:<8}{c(R)} {keeper['file_path']}:{keeper['line_number']}"
              f"   x{len(members)}  {c(D)}[{', '.join(tools)}]{c(R)}")
        for m in members:
            mark = f" {c(GR)}<- primary{c(R)}" if m is keeper else ""
            print(f"      · {m['tool']:<12} {m['severity']:<8} {m['rule_id']}{mark}")
    print()
    print(f"{c(D)}  (đọc-only; DB không đổi — chạy lại bao nhiêu lần cũng được){c(R)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

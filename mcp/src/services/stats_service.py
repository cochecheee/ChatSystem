"""Stats service — pre-aggregate counts cho dashboard KPIs.

Tách ra để dashboard không cần load 200+ findings rồi compute client-side.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories import ArtifactRepository, FindingRepository
from ..services.github_client import GitHubClient


class StatsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.findings = FindingRepository(session)
        self.artifacts = ArtifactRepository(session)

    async def overview(self, *, project_id: int | None = None) -> dict[str, Any]:
        """KPI cards cho Overview page. project_id=None ⇒ aggregate toàn hệ thống."""
        sev = await self.findings.count_by_severity(project_id=project_id)
        status = await self.findings.count_by_status(project_id=project_id)
        tool = await self.findings.count_by_tool(project_id=project_id)
        ai_analyzed = await self.findings.count_ai_analyzed(project_id=project_id)
        total = await self.findings.count_total(project_id=project_id)

        critical = sev.get("critical", 0)
        high = sev.get("high", 0)
        approved = status.get("APPROVED", 0)
        revoked = status.get("REVOKED", 0)
        pending = status.get("pending_review", 0)

        # Per-category open counts so the Vulns badge (SAST-only) and
        # SCA badge (deps-only) match what their pages actually show.
        sast_total = await self.findings.count_with_filters(project_id=project_id, category="sast")
        sast_approved = await self.findings.count_with_filters(project_id=project_id, category="sast", status="APPROVED")
        sast_revoked = await self.findings.count_with_filters(project_id=project_id, category="sast", status="REVOKED")
        deps_total = await self.findings.count_with_filters(project_id=project_id, category="deps")
        deps_approved = await self.findings.count_with_filters(project_id=project_id, category="deps", status="APPROVED")
        deps_revoked = await self.findings.count_with_filters(project_id=project_id, category="deps", status="REVOKED")

        sast_crit = await self.findings.count_with_filters(project_id=project_id, category="sast", severity="critical")
        sast_high = await self.findings.count_with_filters(project_id=project_id, category="sast", severity="high")
        deps_crit = await self.findings.count_with_filters(project_id=project_id, category="deps", severity="critical")
        deps_high = await self.findings.count_with_filters(project_id=project_id, category="deps", severity="high")

        # DAST counts (V2.3 — OWASP ZAP runtime scan)
        dast_total = await self.findings.count_with_filters(project_id=project_id, category="dast")
        dast_approved = await self.findings.count_with_filters(project_id=project_id, category="dast", status="APPROVED")
        dast_revoked = await self.findings.count_with_filters(project_id=project_id, category="dast", status="REVOKED")
        dast_crit = await self.findings.count_with_filters(project_id=project_id, category="dast", severity="critical")
        dast_high = await self.findings.count_with_filters(project_id=project_id, category="dast", severity="high")

        return {
            "total": total,
            "critical_high": critical + high,
            "ai_analyzed": ai_analyzed,
            "ai_analyzed_pct": round(ai_analyzed / total * 100, 1) if total else 0,
            "by_severity": sev,
            "by_status": status,
            "by_tool": tool,
            "open": total - approved - revoked,
            "sast_open": sast_total - sast_approved - sast_revoked,
            "deps_open": deps_total - deps_approved - deps_revoked,
            "dast_open": dast_total - dast_approved - dast_revoked,
            "sast_critical_high": sast_crit + sast_high,
            "deps_critical_high": deps_crit + deps_high,
            "dast_critical_high": dast_crit + dast_high,
            "approved": approved,
            "revoked": revoked,
            "pending": pending,
        }

    async def latest_scan(self, *, project_id: int | None = None) -> dict[str, Any]:
        """Stats cho run mới nhất CÓ findings trong DB (không phải latest GitHub run).

        Dashboard Overview dùng endpoint này để hiển thị "kết quả scan mới nhất".
        Cố gắng enrich với run metadata từ GitHub (run_number, head_branch, created_at);
        nếu GitHub fail thì vẫn trả run_id + counts.
        """
        run_id = await self.artifacts.latest_run_id_with_findings(project_id=project_id)
        if run_id is None:
            return {
                "run_id": None,
                "run_number": None,
                "head_branch": None,
                "created_at": None,
                "scanned_at": None,
                "total": 0,
                "critical_high": 0,
                "ai_analyzed": 0,
                "ai_analyzed_pct": 0,
                "by_severity": {},
                "by_status": {},
                "by_tool": {},
            }

        findings = await self.findings.list_for_run(run_id)
        artifacts = await self.artifacts.list_for_run(run_id)
        scanned_at = max((a.created_at for a in artifacts), default=None)

        total = len(findings)
        sev: dict[str, int] = {}
        status: dict[str, int] = {}
        tool: dict[str, int] = {}
        ai = 0
        for f in findings:
            sev[f.severity] = sev.get(f.severity, 0) + 1
            status[f.status] = status.get(f.status, 0) + 1
            tool[f.tool] = tool.get(f.tool, 0) + 1
            if f.ai_analysis:
                ai += 1

        # Best-effort fetch run metadata from GitHub (may 404 on old runs).
        run_number = None
        head_branch = None
        created_at = None
        try:
            github = GitHubClient()
            run_meta = await github.get_workflow_run(run_id)
            if run_meta:
                run_number = run_meta.get("run_number")
                head_branch = run_meta.get("head_branch")
                created_at = run_meta.get("created_at")
        except Exception:
            pass

        critical_high = sev.get("critical", 0) + sev.get("high", 0)
        return {
            "run_id": run_id,
            "run_number": run_number,
            "head_branch": head_branch,
            "created_at": created_at,
            "scanned_at": scanned_at.isoformat() if scanned_at else None,
            "total": total,
            "critical_high": critical_high,
            "ai_analyzed": ai,
            "ai_analyzed_pct": round(ai / total * 100, 1) if total else 0,
            "by_severity": sev,
            "by_status": status,
            "by_tool": tool,
        }

    async def runs(self, days: int = 30) -> dict[str, Any]:
        """Pass/fail trend cho last N runs từ GitHub Actions.

        Gọi GitHubClient để lấy runs (không persist DB) rồi aggregate
        theo conclusion + theo ngày để vẽ trend chart.
        """
        github = GitHubClient()
        try:
            runs = await github.list_workflow_runs(workflow_name="", branch="", status="")
        except Exception:
            return {"days": days, "total": 0, "by_conclusion": {}, "by_day": {}}

        # Filter trong window
        cutoff = datetime.now(UTC) - timedelta(days=days)
        windowed = []
        for r in runs:
            created = r.get("created_at")
            if not created:
                continue
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt >= cutoff:
                windowed.append((dt, r))

        by_conclusion: dict[str, int] = {}
        by_day: dict[str, dict[str, int]] = {}
        for dt, r in windowed:
            conc = r.get("conclusion") or r.get("status") or "unknown"
            by_conclusion[conc] = by_conclusion.get(conc, 0) + 1
            day = dt.strftime("%Y-%m-%d")
            by_day.setdefault(day, {})
            by_day[day][conc] = by_day[day].get(conc, 0) + 1

        success = by_conclusion.get("success", 0)
        total = len(windowed)

        return {
            "days": days,
            "total": total,
            "pass_rate": round(success / total * 100, 1) if total else 0,
            "by_conclusion": by_conclusion,
            "by_day": by_day,
        }

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import User, enforce_finding_project_access
from ..core.config import settings
from ..models.entities import Artifact, CommandFeedback, Finding
from ..models.schemas import CommandRequest, CommandResponse
from ..services.github_client import GitHubClient
from ..services.llm.service import LLMAnalysisService
from . import report_service

log = logging.getLogger(__name__)

_MIN_JUSTIFICATION = 20


class CommandService:
    def __init__(
        self,
        llm: LLMAnalysisService | None = None,
        github: GitHubClient | None = None,
    ) -> None:
        self._llm = llm or LLMAnalysisService()
        self._github = github or GitHubClient()

    async def handle(
        self,
        cmd: str,
        request: CommandRequest,
        user: User,
        db: AsyncSession,
    ) -> CommandResponse:
        dispatch: dict[str, Any] = {
            "explain":  self._handle_explain,
            "fix":      self._handle_explain,   # same analysis, different framing
            "scan":     self._handle_scan,
            "rerun":    self._handle_rerun,
            "approve":  self._handle_approve,
            "revoke":   self._handle_revoke,
            "report":   self._handle_report,
            # Báo cáo tiến độ docx ch.4.3 — 4 lệnh còn lại
            "status":   self._handle_status,
            "results":  self._handle_results,
            "help":     self._handle_help,
            "feedback": self._handle_feedback,
        }
        return await dispatch[cmd](request, user, db)

    # ------------------------------------------------------------------
    # /explain and /fix
    # ------------------------------------------------------------------

    async def _handle_explain(
        self,
        request: CommandRequest,
        user: User,
        db: AsyncSession,
    ) -> CommandResponse:
        finding = await self._get_finding(request.finding_id, db)

        if finding.status == "ai_analyzed" and finding.ai_analysis:
            data = finding.ai_analysis
        else:
            result = await self._llm.analyze_finding(finding, db)
            data = result.model_dump()

        return CommandResponse(
            status="ok",
            message=f"Phân tích finding #{finding.id} hoàn tất.",
            data=data,
        )

    # ------------------------------------------------------------------
    # /scan
    # ------------------------------------------------------------------

    async def _handle_scan(
        self,
        request: CommandRequest,
        user: User,
        db: AsyncSession,
    ) -> CommandResponse:
        try:
            await self._github.dispatch_workflow("ci.yml")
            log.info("Workflow dispatched by %s", user.username)
            return CommandResponse(
                status="ok",
                message="Đã kích hoạt Security Scan mới trên nhánh main.",
                data={"dispatched_by": user.username},
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"GitHub dispatch failed: {exc}")

    # ------------------------------------------------------------------
    # /rerun
    # ------------------------------------------------------------------

    async def _handle_rerun(
        self,
        request: CommandRequest,
        user: User,
        db: AsyncSession,
    ) -> CommandResponse:
        if not request.run_id:
            raise HTTPException(status_code=422, detail="/rerun cần cung cấp run_id")
        try:
            await self._github.rerun_workflow(request.run_id)
            return CommandResponse(
                status="ok",
                message=f"Đã re-run workflow #{request.run_id}.",
                data={"run_id": request.run_id, "triggered_by": user.username},
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"GitHub rerun failed: {exc}")

    # ------------------------------------------------------------------
    # /approve
    # ------------------------------------------------------------------

    async def _handle_approve(
        self,
        request: CommandRequest,
        user: User,
        db: AsyncSession,
    ) -> CommandResponse:
        finding = await self._get_finding(request.finding_id, db)
        # V3.2 BUG-3 — per-project RBAC for approve action
        await enforce_finding_project_access(
            finding.id, user, db, min_role="security_lead",
        )

        if finding.status == "APPROVED":
            raise HTTPException(status_code=409, detail="Finding này đã được phê duyệt rồi.")

        if (finding.severity or "").upper() == "INFO":
            raise HTTPException(status_code=400, detail="Finding INFO severity không cần approve.")

        justification = (request.justification or "").strip()
        if len(justification) < _MIN_JUSTIFICATION:
            raise HTTPException(
                status_code=422,
                detail=f"Justification phải có ít nhất {_MIN_JUSTIFICATION} ký tự.",
            )

        finding.status = "APPROVED"
        finding.justification = justification
        finding.approved_by = user.username
        finding.approved_at = datetime.now(UTC)
        await db.commit()

        log.info("finding %d approved by %s", finding.id, user.username)
        return CommandResponse(
            status="ok",
            message=f"Finding #{finding.id} đã được phê duyệt bởi {user.username}.",
            data={
                "finding_id": finding.id,
                "approved_by": user.username,
                "approved_at": finding.approved_at.isoformat(),
            },
        )

    # ------------------------------------------------------------------
    # /revoke
    # ------------------------------------------------------------------

    async def _handle_revoke(
        self,
        request: CommandRequest,
        user: User,
        db: AsyncSession,
    ) -> CommandResponse:
        finding = await self._get_finding(request.finding_id, db)
        # V3.2 BUG-3 — per-project RBAC for revoke action
        await enforce_finding_project_access(
            finding.id, user, db, min_role="security_lead",
        )

        if finding.status == "REVOKED":
            raise HTTPException(status_code=409, detail="Finding này đã bị thu hồi rồi.")

        justification = (request.justification or "").strip()
        if len(justification) < _MIN_JUSTIFICATION:
            raise HTTPException(
                status_code=422,
                detail=f"Justification phải có ít nhất {_MIN_JUSTIFICATION} ký tự.",
            )

        finding.status = "REVOKED"
        finding.revoke_justification = justification
        finding.revoked_by = user.username
        finding.revoked_at = datetime.now(UTC)
        await db.commit()

        log.info("finding %d revoked by %s", finding.id, user.username)
        return CommandResponse(
            status="ok",
            message=f"Finding #{finding.id} đã bị thu hồi bởi {user.username}.",
            data={
                "finding_id": finding.id,
                "revoked_by": user.username,
                "revoked_at": finding.revoked_at.isoformat(),
            },
        )

    # ------------------------------------------------------------------
    # /report
    # ------------------------------------------------------------------

    async def _handle_report(
        self,
        request: CommandRequest,
        user: User,
        db: AsyncSession,
    ) -> CommandResponse:
        html_content = await report_service.generate_html(db)
        return CommandResponse(
            status="ok",
            message="Báo cáo HTML đã được tạo.",
            data={"html": html_content},
        )

    # ------------------------------------------------------------------
    # /status  — báo cáo tiến độ docx ch.4.3
    # ------------------------------------------------------------------

    async def _handle_status(
        self,
        request: CommandRequest,
        user: User,
        db: AsyncSession,
    ) -> CommandResponse:
        """Trả về trạng thái workflow run gần nhất của repo configured.

        Repo override (request.repo) chưa thực sự switch GitHub client vì
        runtime đang single-tenant — log warning và dùng repo mặc định.
        """
        if request.repo and request.repo != f"{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}":
            log.info("/status repo override %s ignored — single-tenant runtime", request.repo)
        try:
            runs = await self._github.list_workflow_runs(workflow_name="", branch="", status="")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}")
        if not runs:
            return CommandResponse(
                status="ok",
                message="Chưa có workflow run nào trên repo này.",
                data={"runs": []},
            )
        latest = runs[0]
        in_progress = [r for r in runs if r.get("status") == "in_progress"]
        return CommandResponse(
            status="ok",
            message=(
                f"Run gần nhất: #{latest.get('run_number')} "
                f"({latest.get('conclusion') or latest.get('status')}) "
                f"trên nhánh {latest.get('head_branch')}."
            ),
            data={
                "latest": {
                    "id": latest.get("id"),
                    "run_number": latest.get("run_number"),
                    "status": latest.get("status"),
                    "conclusion": latest.get("conclusion"),
                    "head_branch": latest.get("head_branch"),
                    "head_sha": latest.get("head_sha"),
                    "html_url": latest.get("html_url"),
                    "created_at": latest.get("created_at"),
                },
                "in_progress_count": len(in_progress),
                "repo": f"{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}",
            },
        )

    # ------------------------------------------------------------------
    # /results  — báo cáo tiến độ docx ch.4.3
    # ------------------------------------------------------------------

    async def _handle_results(
        self,
        request: CommandRequest,
        user: User,
        db: AsyncSession,
    ) -> CommandResponse:
        """Tóm tắt findings của run_id chỉ định, hoặc run mới nhất nếu trống.

        Trả severity counts + top 5 critical/high.
        """
        if request.run_id is not None:
            q = (
                select(Artifact.id)
                .where(Artifact.github_run_id == request.run_id)
            )
            artifact_ids = list((await db.execute(q)).scalars().all())
            if not artifact_ids:
                raise HTTPException(
                    status_code=404,
                    detail=f"Không tìm thấy artifact nào cho run_id={request.run_id}.",
                )
            findings_q = (
                select(Finding)
                .where(Finding.artifact_id.in_(artifact_ids))
                .order_by(Finding.severity, desc(Finding.id))
            )
        else:
            # Latest artifact with findings
            latest_q = (
                select(Artifact.id)
                .join(Finding, Finding.artifact_id == Artifact.id)
                .order_by(desc(Artifact.created_at))
                .limit(1)
            )
            latest_id = (await db.execute(latest_q)).scalar_one_or_none()
            if latest_id is None:
                return CommandResponse(
                    status="ok",
                    message="Chưa có scan nào có findings trong DB.",
                    data={"total": 0},
                )
            findings_q = (
                select(Finding)
                .where(Finding.artifact_id == latest_id)
                .order_by(Finding.severity, desc(Finding.id))
            )

        findings = list((await db.execute(findings_q)).scalars().all())
        sev_counts: dict[str, int] = {}
        for f in findings:
            sev_counts[f.severity] = sev_counts.get(f.severity, 0) + 1

        top = [
            {
                "id": f.id,
                "tool": f.tool,
                "rule_id": f.rule_id,
                "severity": f.severity,
                "file_path": f.file_path,
                "line_number": f.line_number,
            }
            for f in findings
            if f.severity in ("critical", "high")
        ][:5]

        crit_high = sev_counts.get("critical", 0) + sev_counts.get("high", 0)
        return CommandResponse(
            status="ok",
            message=(
                f"Tổng cộng {len(findings)} findings"
                + (f" cho run #{request.run_id}" if request.run_id else " (latest scan)")
                + f". Critical/High: {crit_high}."
            ),
            data={
                "total": len(findings),
                "by_severity": sev_counts,
                "top_critical_high": top,
                "run_id": request.run_id,
            },
        )

    # ------------------------------------------------------------------
    # /help  — báo cáo tiến độ docx ch.4.3
    # ------------------------------------------------------------------

    async def _handle_help(
        self,
        request: CommandRequest,
        user: User,
        db: AsyncSession,
    ) -> CommandResponse:
        """Liệt kê 10 lệnh ChatOps + role yêu cầu (docx bảng ch.4.3)."""
        commands = [
            {"name": "/status",   "group": "Monitoring", "args": "[repo]", "roles": ["developer", "security_lead", "admin"], "desc": "Trạng thái pipeline hiện tại."},
            {"name": "/scan",     "group": "Action",     "args": "",                "roles": ["security_lead", "admin"],                "desc": "Kích hoạt scan bảo mật manual."},
            {"name": "/results",  "group": "Monitoring", "args": "[run_id]",         "roles": ["developer", "security_lead", "admin"], "desc": "Tóm tắt kết quả scan."},
            {"name": "/explain",  "group": "Analysis",   "args": "finding_id",       "roles": ["developer", "security_lead", "admin"], "desc": "AI giải thích lỗ hổng (tiếng Việt)."},
            {"name": "/fix",      "group": "Analysis",   "args": "finding_id",       "roles": ["developer", "security_lead", "admin"], "desc": "AI đề xuất diff khắc phục."},
            {"name": "/rerun",    "group": "Action",     "args": "run_id",           "roles": ["security_lead", "admin"],                "desc": "Re-run workflow."},
            {"name": "/approve",  "group": "Action",     "args": "finding_id, justification", "roles": ["security_lead", "admin"],       "desc": "Phê duyệt bypass (≥20 ký tự)."},
            {"name": "/revoke",   "group": "Action",     "args": "finding_id, justification", "roles": ["security_lead", "admin"],       "desc": "Thu hồi phê duyệt."},
            {"name": "/report",   "group": "Monitoring", "args": "",                 "roles": ["developer", "security_lead", "admin"], "desc": "Xuất báo cáo HTML."},
            {"name": "/help",     "group": "General",    "args": "",                 "roles": ["developer", "security_lead", "admin"], "desc": "Danh sách lệnh."},
            {"name": "/feedback", "group": "General",    "args": "[finding_id] text", "roles": ["developer", "security_lead", "admin"], "desc": "Gửi feedback chất lượng AI."},
        ]
        return CommandResponse(
            status="ok",
            message=f"Có {len(commands)} lệnh khả dụng. Role hiện tại: {user.role}.",
            data={"commands": commands, "current_role": user.role},
        )

    # ------------------------------------------------------------------
    # /feedback  — báo cáo tiến độ docx ch.4.3
    # ------------------------------------------------------------------

    async def _handle_feedback(
        self,
        request: CommandRequest,
        user: User,
        db: AsyncSession,
    ) -> CommandResponse:
        """Lưu feedback của user về chất lượng AI analysis.

        Thiếu text → 422. finding_id optional (general feedback OK).
        Persist vào table `command_feedback` để tune prompt/model sau.
        """
        text = (request.feedback_text or "").strip()
        if len(text) < 5:
            raise HTTPException(
                status_code=422,
                detail="feedback_text bắt buộc, tối thiểu 5 ký tự.",
            )
        if request.finding_id is not None:
            # Verify finding exists nếu cung cấp
            if (await db.get(Finding, request.finding_id)) is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Finding #{request.finding_id} không tìm thấy.",
                )

        row = CommandFeedback(
            finding_id=request.finding_id,
            submitted_by=user.username,
            text=text[:2000],
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

        log.info("feedback %d submitted by %s (finding=%s)", row.id, user.username, request.finding_id)
        return CommandResponse(
            status="ok",
            message="Đã ghi nhận phản hồi. Cảm ơn bạn.",
            data={"feedback_id": row.id, "finding_id": request.finding_id},
        )

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    async def _get_finding(self, finding_id: int | None, db: AsyncSession) -> Finding:
        if finding_id is None:
            raise HTTPException(status_code=422, detail="finding_id là bắt buộc cho lệnh này.")
        finding = await db.get(Finding, finding_id)
        if finding is None:
            raise HTTPException(status_code=404, detail=f"Finding #{finding_id} không tìm thấy.")
        return finding

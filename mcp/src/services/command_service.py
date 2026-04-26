from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import User
from ..models.entities import Finding
from ..models.schemas import CommandRequest, CommandResponse
from ..services.llm.service import LLMAnalysisService
from ..services.github_client import GitHubClient
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
            "explain": self._handle_explain,
            "fix":     self._handle_explain,   # same analysis, different framing
            "scan":    self._handle_scan,
            "rerun":   self._handle_rerun,
            "approve": self._handle_approve,
            "revoke":  self._handle_revoke,
            "report":  self._handle_report,
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
    # Helper
    # ------------------------------------------------------------------

    async def _get_finding(self, finding_id: int | None, db: AsyncSession) -> Finding:
        if finding_id is None:
            raise HTTPException(status_code=422, detail="finding_id là bắt buộc cho lệnh này.")
        finding = await db.get(Finding, finding_id)
        if finding is None:
            raise HTTPException(status_code=404, detail=f"Finding #{finding_id} không tìm thấy.")
        return finding

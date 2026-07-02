from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import User, enforce_finding_project_access, get_current_user
from ..core.db import get_session
from ..models.entities import Finding
from ..models.schemas import AnalysisResult
from ..services.llm.service import LLMAnalysisService

log = logging.getLogger(__name__)

router = APIRouter()


def get_llm_service() -> LLMAnalysisService:
    return LLMAnalysisService()


@router.post(
    "/findings/{finding_id}/explain",
    response_model=AnalysisResult,
    summary="Phân tích lỗ hổng bằng Gemini AI",
)
async def explain_finding(
    finding_id: int,
    session: AsyncSession = Depends(get_session),
    service: LLMAnalysisService = Depends(get_llm_service),
    current: User = Depends(get_current_user),
) -> AnalysisResult:
    """Gọi Gemini AI phân tích finding và trả về giải thích tiếng Việt + remediation diff.

    V3.2 — Requires authentication. When RBAC_PER_PROJECT is on, the caller
    must have at least `developer` membership on the finding's project
    (admins always bypass).
    """
    finding = await session.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    await enforce_finding_project_access(
        finding.id, current, session, min_role="developer",
    )

    if finding.status == "ai_analyzed" and finding.ai_analysis:
        return AnalysisResult(**finding.ai_analysis)

    try:
        return await service.analyze_finding(finding, session)
    except ValueError as exc:
        # Layer 4 (InjectionGuardrail) từ chối nội dung nghi prompt injection
        # trước khi gọi LLM → trả 422 rõ ràng để UI hiển thị thay vì 500.
        log.warning("Guardrail blocked finding %d: %s", finding_id, exc)
        raise HTTPException(
            status_code=422,
            detail="Nội dung finding bị guardrail từ chối (nghi prompt injection) — không gửi tới AI.",
        )
    except RuntimeError as exc:
        log.error("Gemini failed for finding %d: %s", finding_id, exc)
        raise HTTPException(status_code=503, detail=f"AI service unavailable: {exc}")

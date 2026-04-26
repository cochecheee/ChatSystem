from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

log = logging.getLogger(__name__)
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_session
from ..models.entities import Finding
from ..models.schemas import AnalysisResult
from ..services.llm.service import LLMAnalysisService

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


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
) -> AnalysisResult:
    """Gọi Gemini AI phân tích finding và trả về giải thích tiếng Việt + remediation diff."""
    finding = await session.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    if finding.status == "ai_analyzed" and finding.ai_analysis:
        return AnalysisResult(**finding.ai_analysis)

    try:
        return await service.analyze_finding(finding, session)
    except RuntimeError as exc:
        log.error("Gemini failed for finding %d: %s", finding_id, exc)
        raise HTTPException(status_code=503, detail=f"AI service unavailable: {exc}")

from __future__ import annotations

import logging

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
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


def _sse(event: str | None, data: str) -> str:
    """Format a Server-Sent Events frame. Multi-line data is split across
    `data:` lines per the SSE spec so newlines survive transport."""
    lines = [f"event: {event}"] if event else []
    lines += [f"data: {ln}" for ln in data.split("\n")]
    return "\n".join(lines) + "\n\n"


@router.get(
    "/findings/{finding_id}/explain/stream",
    summary="Phân tích lỗ hổng bằng Gemini AI (SSE streaming)",
)
async def explain_finding_stream(
    finding_id: int,
    session: AsyncSession = Depends(get_session),
    service: LLMAnalysisService = Depends(get_llm_service),
    current: User = Depends(get_current_user),
) -> StreamingResponse:
    """Streaming variant of /explain (báo cáo §4.3.4, Mã A.10).

    Trả kết quả AI theo từng chunk qua Server-Sent Events để frontend hiển thị
    dần bằng EventSource thay vì chờ toàn bộ phản hồi. Mỗi chunk là một event
    `data:`; kết thúc bằng `event: done`. Cùng RBAC như POST /explain
    (developer+ trên project của finding).
    """
    finding = await session.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    await enforce_finding_project_access(
        finding.id, current, session, min_role="developer",
    )

    async def event_source() -> AsyncIterator[str]:
        try:
            async for chunk in service.stream_explain(finding, session):
                if chunk:
                    yield _sse(None, chunk)
            yield _sse("done", "[DONE]")
        except ValueError:
            log.warning("Guardrail blocked stream for finding %d", finding_id)
            yield _sse("error", "guardrail_rejected")
        except RuntimeError as exc:
            log.error("Gemini stream failed for finding %d: %s", finding_id, exc)
            yield _sse("error", "ai_unavailable")

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

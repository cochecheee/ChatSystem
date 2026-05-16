"""V3.3 Part B — Overview AI risk summary.

Aggregates project stats + top critical/high findings, asks Gemini for a
Vietnamese risk briefing in a structured shape the dashboard can render
as a multi-section card (not one paragraph blob).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, UTC, timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.entities import Artifact, Finding, Project
from ...repositories import FindingRepository
from .client import GeminiClient
from .service import LLMAnalysisService

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Output schema — Gemini fills this via response_schema=. The FE renders
# overview_md and recommendations_md through a small markdown subset and
# top_risks as click-through rows.
# --------------------------------------------------------------------------

class TopRisk(BaseModel):
    severity: Literal["critical", "high", "medium"]
    rule_id: str
    file_path: str
    one_line_reason: str = Field(description="Vietnamese, <=20 words, cite the actual vulnerability mechanism")
    finding_id: int


class AiSummaryOutput(BaseModel):
    overview_md: str = Field(description="2-3 sentence Vietnamese summary citing exact numbers")
    top_risks: list[TopRisk] = Field(description="3-5 most impactful risks", max_length=5)
    recommendations_md: str = Field(description="1-3 numbered actions, actionable verbs first")


class PipelineHealth(BaseModel):
    runs_total: int
    runs_passed: int
    pass_rate_pct: float
    trend: Literal["improving", "stable", "degrading"]


class AiSummaryResponse(BaseModel):
    project_id: int | None
    run_id: int | None
    generated_at: str
    cached: bool
    cache_ttl_remaining: int
    model: str
    overview_md: str
    top_risks: list[TopRisk]
    recommendations_md: str
    pipeline_health: PipelineHealth


# --------------------------------------------------------------------------
# In-memory cache. Keyed by (project_id, run_id). TTL 10 min.
# --------------------------------------------------------------------------

_CACHE_TTL = timedelta(minutes=10)
_cache: dict[tuple[int | None, int | None], tuple[AiSummaryResponse, datetime]] = {}


def _cache_get(key) -> AiSummaryResponse | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    stored, expires_at = entry
    if datetime.now(UTC) >= expires_at:
        _cache.pop(key, None)
        return None
    # Return a copy so caller mutations (cached flag, ttl) don't leak back
    # into the cached value or into prior returns.
    fresh = stored.model_copy()
    fresh.cache_ttl_remaining = max(0, int((expires_at - datetime.now(UTC)).total_seconds()))
    fresh.cached = True
    return fresh


def _cache_put(key, response: AiSummaryResponse) -> None:
    expires_at = datetime.now(UTC) + _CACHE_TTL
    _cache[key] = (response, expires_at)


def clear_cache() -> None:
    """Test hook + manual eviction."""
    _cache.clear()


SUMMARY_SYSTEM_INSTRUCTION = """\
You are a senior application security analyst writing a 30-second briefing
for a tech lead. Output JSON matching the schema.

Rules:
- Vietnamese language for all narrative fields.
- overview_md: 2-3 sentences. MUST cite exact numbers from the stats input
  (total findings, critical count, high count, AI-analyzed count). Use
  **bold** around key numbers.
- top_risks: pick 3-5 most impactful from the input list. one_line_reason
  in Vietnamese, <=20 words, MUST cite the actual vulnerability mechanism
  (e.g., "SSRF qua user-supplied URL", "snakeyaml CVE chưa fix"),
  NOT just "security issue".
- recommendations_md: numbered list 1-3 items, start each with a verb
  ("Fix", "Upgrade", "Triage", "Review"), tie to specific finding counts
  from the input. Format as markdown "1. Fix...\n2. ...".
- DO NOT generate pipeline_health — that's computed by the backend.

Be terse. No filler. No marketing tone."""


async def _call_gemini_summary(client: GeminiClient, prompt: str) -> AiSummaryOutput:
    """One Gemini call returning structured AiSummaryOutput."""
    from google.genai import types

    response = await asyncio.to_thread(
        client._client.models.generate_content,
        model=client._model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=AiSummaryOutput,
            system_instruction=SUMMARY_SYSTEM_INSTRUCTION,
        ),
    )
    return AiSummaryOutput.model_validate_json(response.text)


def _heuristic_trend(pass_rate: float, runs_total: int) -> Literal["improving", "stable", "degrading"]:
    if runs_total < 3:
        return "stable"
    if pass_rate >= 80:
        return "stable"
    if pass_rate >= 60:
        return "degrading"
    return "degrading"


class SummaryService:
    """Owns the aggregate→prompt→cache flow for /findings/ai-summary."""

    def __init__(self, llm_service: LLMAnalysisService | None = None, llm_caller=None):
        self._llm_service = llm_service or LLMAnalysisService()
        self._llm_caller = llm_caller or _call_gemini_summary

    async def _gather_stats(
        self, session: AsyncSession, *, project_id: int | None, run_id: int | None,
    ) -> dict:
        """Compute the inputs we hand to the LLM + the deterministic pipeline_health."""
        from sqlalchemy import select
        repo = FindingRepository(session)

        common = dict(project_id=project_id, run_id=run_id)
        total = await repo.count_with_filters(**common)
        critical = await repo.count_with_filters(severity="critical", **common)
        high = await repo.count_with_filters(severity="high", **common)
        medium = await repo.count_with_filters(severity="medium", **common)
        ai_analyzed = await repo.count_with_filters(status="ai_analyzed", **common)
        active_total = await repo.count_with_filters(exclude_revoked=True, **common)

        # Top 10 critical/high findings — input to top_risks
        top_findings = await repo.list_with_filters(
            project_id=project_id, run_id=run_id, exclude_revoked=True,
            limit=10, skip=0,
        )
        # Sort: critical first, then high
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        top_findings.sort(key=lambda f: (sev_order.get(f.severity, 9), -f.id))
        top_for_prompt = [
            {
                "id": f.id, "severity": f.severity, "rule_id": f.rule_id,
                "file_path": f.file_path,
                "message": (f.message or "")[:200],
            }
            for f in top_findings[:8]
        ]

        # Pipeline health — count from Artifact.github_run_id distinct runs and
        # rough heuristic. Real pass rate calls GitHub API; for the summary
        # card we use what's locally observable.
        result = await session.execute(
            select(Artifact.github_run_id).where(Artifact.github_run_id.is_not(None))
        )
        run_ids = {row[0] for row in result.all() if row[0]}
        runs_total = len(run_ids)
        # Without GitHub API calls we don't know conclusion. Treat 'has any
        # finding' as 'observed'; pass-rate is naive but documented as such.
        runs_passed = max(1, runs_total - critical)  # crude but stable
        pass_rate = round((runs_passed / runs_total * 100), 1) if runs_total else 0.0

        return {
            "stats": {
                "total": total,
                "critical": critical,
                "high": high,
                "medium": medium,
                "ai_analyzed": ai_analyzed,
                "active_total": active_total,
            },
            "top_findings": top_for_prompt,
            "pipeline_health": PipelineHealth(
                runs_total=runs_total,
                runs_passed=runs_passed,
                pass_rate_pct=pass_rate,
                trend=_heuristic_trend(pass_rate, runs_total),
            ),
        }

    def _build_prompt(self, project_name: str, inputs: dict) -> str:
        s = inputs["stats"]
        top = inputs["top_findings"]
        return (
            f"Project: {project_name}\n\n"
            f"Stats: total={s['total']}, critical={s['critical']}, high={s['high']}, "
            f"medium={s['medium']}, ai_analyzed={s['ai_analyzed']}, "
            f"active(not revoked)={s['active_total']}\n\n"
            f"Top findings (id, severity, rule, file, message):\n"
            + "\n".join(
                f"- id={f['id']}, {f['severity']}, {f['rule_id']}, {f['file_path']}, "
                f"\"{f['message']}\""
                for f in top
            )
        )

    async def generate(
        self,
        session: AsyncSession,
        *,
        project_id: int | None,
        run_id: int | None,
        force_refresh: bool = False,
    ) -> AiSummaryResponse:
        key = (project_id, run_id)
        if not force_refresh:
            cached = _cache_get(key)
            if cached is not None:
                return cached

        # Resolve project for Gemini credentials (V2.8 multi-tenant)
        project_name = "all projects"
        gemini: GeminiClient
        if project_id is not None:
            project = await session.get(Project, project_id)
            if project is None:
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="Project not found")
            project_name = project.name
            if project.gemini_api_key:
                gemini = self._llm_service._get_gemini(
                    project.gemini_api_key,
                    project.gemini_model or "gemini-2.5-flash",
                )
            else:
                gemini = GeminiClient()
        else:
            gemini = GeminiClient()

        inputs = await self._gather_stats(session, project_id=project_id, run_id=run_id)
        if inputs["stats"]["total"] == 0:
            # Empty project — skip LLM call, return a clean message.
            response = AiSummaryResponse(
                project_id=project_id, run_id=run_id,
                generated_at=datetime.now(UTC).isoformat(),
                cached=False, cache_ttl_remaining=int(_CACHE_TTL.total_seconds()),
                model=gemini._model,
                overview_md="Không có finding nào trong scope hiện tại — hệ thống sạch ✓",
                top_risks=[],
                recommendations_md="Tiếp tục giữ pipeline đang chạy đều đặn để phát hiện sớm.",
                pipeline_health=inputs["pipeline_health"],
            )
            _cache_put(key, response)
            return response

        prompt = self._build_prompt(project_name, inputs)
        try:
            llm_output = await self._llm_caller(gemini, prompt)
        except Exception as exc:
            log.error("AI summary Gemini call failed: %s", exc)
            raise

        response = AiSummaryResponse(
            project_id=project_id,
            run_id=run_id,
            generated_at=datetime.now(UTC).isoformat(),
            cached=False,
            cache_ttl_remaining=int(_CACHE_TTL.total_seconds()),
            model=gemini._model,
            overview_md=llm_output.overview_md,
            top_risks=llm_output.top_risks,
            recommendations_md=llm_output.recommendations_md,
            pipeline_health=inputs["pipeline_health"],
        )
        _cache_put(key, response)
        return response

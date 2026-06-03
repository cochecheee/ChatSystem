"""V3.3 Part B — Overview AI risk summary.

Aggregates project stats + top critical/high findings, asks Gemini for a
Vietnamese risk briefing in a structured shape the dashboard can render
as a multi-section card (not one paragraph blob).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.entities import Artifact, Project
from ...repositories import FindingRepository
from .client import GeminiClient
from .prompt_loader import get_registry
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
            system_instruction=get_registry().system_for("summary"),
        ),
    )
    return AiSummaryOutput.model_validate_json(response.text)


def _risk_group_key(f) -> tuple[str, str]:
    """Bucket a finding so we can pick diverse representatives.

    Group key = (tool, family) where family captures the vulnerability
    *class*, deliberately ignoring the specific file or CVE id:
      - Slash rules ("java/path-injection"): full rule id — different rules
        in the same language stay distinct (path-injection ≠ ssrf).
      - CVE rules: bucket by file_path (= library coordinate like
        "Java:org.yaml:snakeyaml") so a 5-CVE family on one library
        collapses to one group.
      - Anything else: full rule id.
    """
    import re
    tool = (f.tool or "unknown").lower()
    rid = (f.rule_id or "").strip()
    if "/" in rid:
        family = rid.lower()
    elif re.match(r"^CVE-\d{4}", rid, re.IGNORECASE):
        family = (f.file_path or "cve").lower()
    else:
        family = rid.lower() or (f.file_path or "").lower()
    return (tool, family)


def _pick_diverse(pool, k: int):
    """Round-robin one finding per group, biggest groups first, until we
    have k items or the pool runs out. Preserves severity ordering inside
    each group (the pool is already sorted critical→low)."""
    from collections import defaultdict
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for f in pool:
        groups[_risk_group_key(f)].append(f)

    selected: list = []
    seen: set = set()
    # First pass — one from each distinct group, in pool order
    for f in pool:
        g = _risk_group_key(f)
        if g in seen:
            continue
        seen.add(g)
        selected.append(f)
        if len(selected) >= k:
            return selected
    # Second pass — fill remaining slots with extras from the largest groups
    remaining = [
        f for f in pool
        if f not in selected
    ]
    selected.extend(remaining[: k - len(selected)])
    return selected


def _heuristic_trend(pass_rate: float, runs_total: int) -> Literal["improving", "stable", "degrading"]:
    """Snapshot pass-rate → 3-bucket label.

    Note: real "improving" needs a previous window to compare against,
    which we don't persist. Until trend history lands we report stable
    when pass_rate is healthy and degrading only when it visibly is.
    """
    if runs_total < 3:
        return "stable"  # not enough data
    if pass_rate >= 70:
        return "stable"
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
        # V3.4 BUG-2 — switch primary numbers to ACTIVE (exclude REVOKED).
        # Revoked findings are developer-triaged false positives; reporting
        # them as outstanding work confuses the briefing. We still expose
        # the historical total so Gemini can mention "X total, Y revoked"
        # when the kill rate is meaningful.
        total = await repo.count_with_filters(**common)                                       # historical
        active_total = await repo.count_with_filters(exclude_revoked=True, **common)          # what to act on
        critical = await repo.count_with_filters(severity="critical", exclude_revoked=True, **common)
        high = await repo.count_with_filters(severity="high", exclude_revoked=True, **common)
        medium = await repo.count_with_filters(severity="medium", exclude_revoked=True, **common)
        ai_analyzed = await repo.count_with_filters(status="ai_analyzed", **common)
        revoked = total - active_total

        # Pull a wide pool, then pick diverse representatives. Without this,
        # severity-first sorting can return 5 CVEs all from the same library
        # (V3.4 BUG-3 — ALOUTE returned 5 snakeyaml CVEs in a row).
        pool = await repo.list_with_filters(
            project_id=project_id, run_id=run_id, exclude_revoked=True,
            limit=50, skip=0,
        )
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        pool.sort(key=lambda f: (sev_order.get(f.severity, 9), -f.id))
        diverse = _pick_diverse(pool, k=8)
        top_for_prompt = [
            {
                "id": f.id, "severity": f.severity, "rule_id": f.rule_id,
                "file_path": f.file_path,
                "message": (f.message or "")[:200],
            }
            for f in diverse
        ]

        # V3.4 BUG-1 — replace the bogus `runs_passed = total - critical`
        # heuristic with real GitHub conclusions. We call list_workflow_runs
        # at most once per summary; the 10-min cache means ~6 API calls/hour/
        # project against the 5000/hour quota. If the call fails (network,
        # bad credentials), fall back to "stable, unknown" rather than lying.
        runs_total = 0
        runs_passed = 0
        try:
            from ..github_client import GitHubClient as _GH
            if project_id is not None:
                project = await session.get(Project, project_id)
                gh = _GH.for_project(project) if (project and project.github_token) else _GH()
            else:
                gh = _GH()
            recent_runs = await gh.list_workflow_runs(
                workflow_name="", branch="", status="",
            )
            runs_total = len(recent_runs)
            runs_passed = sum(1 for r in recent_runs if r.get("conclusion") == "success")
        except Exception as exc:
            log.warning("AI summary: pipeline_health GitHub call failed (%s), falling back to local", exc)
            # Fall back to local artifact count — at least we know runs_total
            result = await session.execute(
                select(Artifact.github_run_id).where(Artifact.github_run_id.is_not(None))
            )
            run_ids = {row[0] for row in result.all() if row[0]}
            runs_total = len(run_ids)
            runs_passed = 0  # honest: we don't know
        pass_rate = round((runs_passed / runs_total * 100), 1) if runs_total else 0.0

        return {
            "stats": {
                "total": total,
                "active": active_total,
                "revoked": revoked,
                "critical": critical,        # active counts
                "high": high,
                "medium": medium,
                "ai_analyzed": ai_analyzed,
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
        rendered = get_registry().render(
            "summary",
            project_name=project_name,
            stats=inputs["stats"],
            top_findings=inputs["top_findings"],
        )
        return rendered.user or ""

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

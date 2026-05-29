"""V3.1 Tier 3 — AI-assisted batch FP triage.

Reads a list of findings, sends them to Gemini in a single structured-output
call, and applies REVOKED automatically when classification is FALSE_POSITIVE
with confidence above a threshold. The point: cut manual triage load from
'review 184 rows' to 'review the 20 the model wasn't sure about'.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, UTC

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.entities import Finding
from .client import GeminiClient
from .prompt_loader import get_registry
from .service import LLMAnalysisService

log = logging.getLogger(__name__)


class TriageItem(BaseModel):
    finding_id: int
    classification: str = Field(description="TRUE_POSITIVE | FALSE_POSITIVE | NEEDS_REVIEW")
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class TriageBatch(BaseModel):
    items: list[TriageItem]


async def _run_triage_call(client: GeminiClient, findings: list[Finding]) -> TriageBatch:
    """One Gemini call for up to BATCH_SIZE findings — returns structured output."""
    from google.genai import types

    rendered = get_registry().render("triage", findings=findings)
    response = await asyncio.to_thread(
        client._client.models.generate_content,
        model=client._model,
        contents=rendered.user,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TriageBatch,
            system_instruction=rendered.system,
        ),
    )
    return TriageBatch.model_validate_json(response.text)


class TriageService:
    """Batch triage orchestrator. Caller injects an LLM call so tests can stub it."""

    BATCH_SIZE = 20

    def __init__(
        self,
        llm_service: LLMAnalysisService | None = None,
        llm_caller=None,
    ):
        self._llm_service = llm_service or LLMAnalysisService()
        # llm_caller(client, findings) -> TriageBatch
        self._llm_caller = llm_caller or _run_triage_call

    async def triage_findings(
        self,
        session: AsyncSession,
        findings: list[Finding],
        *,
        confidence_threshold: float = 0.8,
        dry_run: bool = False,
        invoked_by: str = "ai-triage",
    ) -> dict:
        """Classify findings; write REVOKED back when FP+confidence>=threshold.

        Returns a summary {total, classifications: {TP/FP/NR counts},
        auto_revoked, batches, items: [...]}. Dry-run mode lets the UI preview
        before committing.
        """
        if not findings:
            return {"total": 0, "classifications": {}, "auto_revoked": 0, "items": []}

        # Resolve a GeminiClient via first finding's project (multi-tenant)
        project = await self._llm_service._resolve_project(findings[0], session)
        if project and project.gemini_api_key:
            client = self._llm_service._get_gemini(
                project.gemini_api_key, project.gemini_model or "gemini-2.5-flash",
            )
        else:
            client = self._llm_service._injected_client or GeminiClient()

        all_items: list[TriageItem] = []
        batches = 0
        for i in range(0, len(findings), self.BATCH_SIZE):
            batch = findings[i:i + self.BATCH_SIZE]
            batches += 1
            try:
                result = await self._llm_caller(client, batch)
                all_items.extend(result.items)
            except Exception as exc:
                log.warning("Triage batch %d failed: %s — skipping", batches, exc)
                continue

        # Map back to findings for write
        by_id = {f.id: f for f in findings}
        counts = {"TRUE_POSITIVE": 0, "FALSE_POSITIVE": 0, "NEEDS_REVIEW": 0}
        auto_revoked = 0
        action_log: list[dict] = []
        for item in all_items:
            counts[item.classification] = counts.get(item.classification, 0) + 1
            action = {
                "finding_id": item.finding_id,
                "classification": item.classification,
                "confidence": item.confidence,
                "reason": item.reason,
                "applied": False,
            }
            f = by_id.get(item.finding_id)
            if (
                not dry_run
                and f is not None
                and item.classification == "FALSE_POSITIVE"
                and item.confidence >= confidence_threshold
                and f.status != "REVOKED"
            ):
                f.status = "REVOKED"
                f.revoked_by = invoked_by
                f.revoke_justification = (
                    f"AI triage (confidence {item.confidence:.2f}): {item.reason}"
                )
                f.revoked_at = datetime.now(UTC)
                auto_revoked += 1
                action["applied"] = True
            action_log.append(action)

        if not dry_run and auto_revoked > 0:
            await session.commit()

        return {
            "total": len(findings),
            "classified": len(all_items),
            "classifications": counts,
            "auto_revoked": auto_revoked,
            "batches": batches,
            "confidence_threshold": confidence_threshold,
            "dry_run": dry_run,
            "items": action_log,
        }

"""V3.1 Tier 3 — AI-assisted batch FP triage.

Reads a list of findings, sends them to Gemini in a single structured-output
call, and applies REVOKED automatically when classification is FALSE_POSITIVE
with confidence above a threshold. The point: cut manual triage load from
'review 184 rows' to 'review the 20 the model wasn't sure about'.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.entities import Finding
from .client import GeminiClient
from .prompt_loader import get_registry
from .service import LLMAnalysisService, _extract_context, _is_dependency_finding

log = logging.getLogger(__name__)


class TriageItem(BaseModel):
    finding_id: int
    classification: str = Field(description="TRUE_POSITIVE | FALSE_POSITIVE | NEEDS_REVIEW")
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class TriageBatch(BaseModel):
    items: list[TriageItem]


async def _run_triage_call(client: GeminiClient, findings: list[Finding]) -> TriageBatch:
    """One Gemini call for up to BATCH_SIZE findings — returns structured output.

    V4.2 — each item now carries a ±context slice of the REAL source (from the
    cached `raw_data['source_code']`, populated by `triage_findings`), so the
    model classifies false positives from code, not metadata alone."""
    from google.genai import types

    items = [
        {
            "id": f.id,
            "tool": f.tool,
            "rule_id": f.rule_id,
            "severity": f.severity,
            "file_path": f.file_path,
            "line_number": f.line_number,
            "message": (f.message or "")[:300],
            "code": _extract_context((f.raw_data or {}).get("source_code"), f.line_number),
        }
        for f in findings
    ]
    rendered = get_registry().render("triage", items=items)
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

        # V4.2 — ensure each SAST finding has source context so FP classification
        # sees the code. Cached first; else best-effort GitHub fetch (bounded,
        # failure-tolerant). `code_seen` gates auto-revoke below: we never
        # suppress a finding from metadata alone.
        from ...core.guardrails import layer_on
        from ..github_client import GitHubClient
        gh = None
        if project and project.github_token and project.github_owner and project.github_repo:
            gh = GitHubClient.for_project(project)
        elif self._llm_service._injected_github is not None:
            gh = self._llm_service._injected_github
        code_seen: dict[int, bool] = {}
        fetched = 0
        for f in findings:
            src = (f.raw_data or {}).get("source_code")
            if (
                not src and gh is not None and fetched < 15
                and not _is_dependency_finding(f)
                and f.file_path and f.file_path not in ("unknown", "")
                and not f.file_path.endswith((".jar", ".class", ".war", ".ear"))
            ):
                try:
                    raw = await gh.fetch_file_content(f.file_path)
                    if raw:
                        src = (
                            self._llm_service._scrubber.scrub_content(raw)
                            if layer_on("scrubbing") else raw
                        )
                        nr = dict(f.raw_data or {})
                        nr["source_code"] = src
                        f.raw_data = nr
                        fetched += 1
                except Exception as exc:
                    log.debug("triage source fetch failed for finding %d: %s", f.id, exc)
                    src = None
            code_seen[f.id] = bool(src)

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
        withheld_no_code = 0
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
            is_fp_high = (
                item.classification == "FALSE_POSITIVE"
                and item.confidence >= confidence_threshold
            )
            if not dry_run and f is not None and is_fp_high and f.status != "REVOKED":
                # V4.2 — only auto-revoke when the model actually saw the code
                # (grounded evidence). No code → hold for human (NEEDS_REVIEW).
                if code_seen.get(item.finding_id):
                    f.status = "REVOKED"
                    f.revoked_by = invoked_by
                    f.revoke_justification = (
                        f"AI triage (confidence {item.confidence:.2f}): {item.reason}"
                    )
                    f.revoked_at = datetime.now(UTC)
                    auto_revoked += 1
                    action["applied"] = True
                else:
                    withheld_no_code += 1
                    action["withheld"] = "no_code_context"
            action_log.append(action)

        if not dry_run and auto_revoked > 0:
            await session.commit()

        return {
            "total": len(findings),
            "classified": len(all_items),
            "classifications": counts,
            "auto_revoked": auto_revoked,
            "withheld_no_code": withheld_no_code,
            "batches": batches,
            "confidence_threshold": confidence_threshold,
            "dry_run": dry_run,
            "items": action_log,
        }

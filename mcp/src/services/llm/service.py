from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.entities import Finding
from ...models.schemas import AnalysisResult
from ..github_client import GitHubClient
from ...core.guardrails import ScrubbingService
from .client import GeminiClient
from .prompts import build_prompt
from .schemas import AnalysisOutput

log = logging.getLogger(__name__)

_CONTEXT_LINES = 15  # lines before and after the vulnerable line


def _extract_context(source_code: str | None, line_number: int | None) -> str:
    if not source_code or not line_number:
        return ""
    lines = source_code.splitlines()
    start = max(0, line_number - 1 - _CONTEXT_LINES)
    end = min(len(lines), line_number + _CONTEXT_LINES)
    numbered = [f"{i + 1:4d} | {l}" for i, l in enumerate(lines[start:end], start=start)]
    return "\n".join(numbered)


class LLMAnalysisService:
    def __init__(
        self,
        client: GeminiClient | None = None,
        github_client: GitHubClient | None = None,
    ) -> None:
        self._client = client or GeminiClient()
        self._github_client = github_client or GitHubClient()
        self._scrubber = ScrubbingService()

    async def analyze_finding(
        self,
        finding: Finding,
        session: AsyncSession,
    ) -> AnalysisResult:
        source_code: str | None = None
        raw = finding.raw_data or {}
        source_code = raw.get("source_code")

        # Fetch live from GitHub if not cached and path is a real source file
        if (
            not source_code
            and finding.file_path
            and finding.file_path not in ("unknown", "")
            and not finding.file_path.endswith((".jar", ".class", ".war", ".ear"))
        ):
            try:
                fetched = await self._github_client.fetch_file_content(finding.file_path)
                if fetched:
                    # Scrub for PII/secrets before storing or passing to Gemini
                    source_code = self._scrubber.scrub_content(fetched)
                    raw = dict(finding.raw_data or {})
                    raw["source_code"] = source_code
                    finding.raw_data = raw
                    # session.commit() at end of method persists the cache
            except Exception as exc:
                log.warning("Could not fetch source for finding %d: %s", finding.id, exc)

        code_context = _extract_context(source_code, finding.line_number)

        prompt = build_prompt(
            tool_name=finding.tool,
            rule_id=finding.rule_id,
            message=finding.message,
            file_path=finding.file_path,
            line_number=finding.line_number,
            cwe_id=finding.cwe_id,
            cvss_score=finding.cvss_score,
            code_context=code_context,
        )

        output: AnalysisOutput = await self._client.analyze(prompt)

        result = AnalysisResult(
            finding_id=finding.id,
            vulnerability_id=output.vulnerability_id,
            explanation_vi=output.explanation_vi,
            impact_vi=output.impact_vi,
            remediation_diff=output.remediation_diff,
            severity=output.severity,
            cwe_reference=output.cwe_reference,
            confidence=output.confidence,
        )

        finding.status = "ai_analyzed"
        finding.ai_analysis = result.model_dump()
        await session.commit()

        log.info("finding %d analyzed by Gemini (confidence=%s)", finding.id, output.confidence)
        return result

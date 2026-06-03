from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import settings
from ...core.guardrails import InjectionGuardrail, ScrubbingService
from ...models.entities import Artifact, Finding, Project
from ...models.schemas import AnalysisResult
from ..github_client import GitHubClient
from .client import GeminiClient
from .prompt_loader import get_registry
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
        # Khi client/github_client truyền explicit (test injection) → giữ.
        # Khi None → V2.8 B4: build từ project credentials per-call.
        self._injected_client = client
        self._injected_github = github_client
        self._scrubber = ScrubbingService()
        self._guardrail = InjectionGuardrail()
        # Cache GeminiClient theo (api_key, model) tránh tạo lại mỗi finding
        self._gemini_cache: dict[tuple[str, str], GeminiClient] = {}

    async def _resolve_project(
        self, finding: Finding, session: AsyncSession,
    ) -> Project | None:
        """Truy ngược Finding → Artifact → Project để lấy credentials.

        Trả None nếu chain bị đứt — caller fallback env client.
        """
        artifact = await session.get(Artifact, finding.artifact_id)
        if artifact is None:
            return None
        return await session.get(Project, artifact.project_id)

    def _get_gemini(self, api_key: str, model: str) -> GeminiClient:
        cache_key = (api_key, model)
        client = self._gemini_cache.get(cache_key)
        if client is None:
            client = GeminiClient(api_key=api_key, model=model)
            self._gemini_cache[cache_key] = client
        return client

    async def analyze_finding(
        self,
        finding: Finding,
        session: AsyncSession,
    ) -> AnalysisResult:
        # B4 — resolve project để chọn credentials Gemini + GitHub fetch
        project = None
        if not self._injected_client or not self._injected_github:
            project = await self._resolve_project(finding, session)

        if self._injected_github is not None:
            github_client = self._injected_github
        elif project and project.github_token and project.github_owner and project.github_repo:
            github_client = GitHubClient.for_project(project)
        else:
            github_client = GitHubClient()

        if self._injected_client is not None:
            gemini = self._injected_client
        elif project and project.gemini_api_key:
            gemini = self._get_gemini(
                project.gemini_api_key,
                project.gemini_model or settings.GEMINI_MODEL,
            )
        else:
            gemini = self._get_gemini(
                settings.GEMINI_API_KEY,
                settings.GEMINI_MODEL,
            )

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
                fetched = await github_client.fetch_file_content(finding.file_path)
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

        # Defend against indirect prompt injection: SAST finding messages and
        # code context come from untrusted sources (open-source repos, CI
        # tools). Reject obvious injection patterns; sanitize anything that
        # passes (truncate, strip control chars) before it hits Gemini.
        safe_message, reason_msg = self._guardrail.check(finding.message or "")
        safe_context, reason_ctx = self._guardrail.check(code_context)
        if not safe_message or not safe_context:
            log.warning(
                "Injection guardrail blocked finding %d: msg=%r ctx=%r",
                finding.id, reason_msg, reason_ctx,
            )
            raise ValueError("Finding content rejected by injection guardrail")

        rendered = get_registry().render(
            "analyze",
            tool_name=finding.tool,
            rule_id=finding.rule_id,
            message=self._guardrail.sanitize(finding.message or ""),
            file_path=finding.file_path,
            line_number=finding.line_number,
            cwe_id=finding.cwe_id,
            cvss_score=finding.cvss_score,
            code_context=self._guardrail.sanitize(code_context),
        )
        prompt = rendered.user or ""

        output: AnalysisOutput = await gemini.analyze(prompt)

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

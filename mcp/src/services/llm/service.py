from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import settings
from ...core.guardrails import InjectionGuardrail, ScrubbingService, layer_on
from ...models.entities import Artifact, Finding, Project
from ...models.schemas import AnalysisResult, FPInvestigation, InvestigationStep
from ...repositories.finding_repo import DEPS_TOOLS
from ..github_client import GitHubClient
from .client import GeminiClient
from .prompt_loader import get_registry
from .schemas import AnalysisOutput

log = logging.getLogger(__name__)

_CONTEXT_LINES = 15  # lines before and after the vulnerable line

# Rule-id prefixes that mark a dependency/advisory finding even when the tool
# isn't in DEPS_TOOLS (e.g. a Semgrep supply-chain rule that emits a GHSA id).
_ADVISORY_RE = re.compile(r"^(CVE|GHSA|SNYK|PRISMA|RUSTSEC)-", re.IGNORECASE)


def _is_dependency_finding(finding: Finding) -> bool:
    """True khi finding là lỗ hổng thư viện phụ thuộc (SCA/CVE) — cần fix bằng
    nâng cấp phiên bản chứ không phải sửa mã nguồn."""
    if finding.tool in DEPS_TOOLS:
        return True
    return bool(_ADVISORY_RE.match(finding.rule_id or ""))


def _dep_meta(finding: Finding) -> dict[str, str]:
    """Trích package/version/CVE từ raw_data (chuẩn hoá khoá Trivy + Dep-Check)."""
    d = finding.raw_data or {}

    def pick(*keys: str) -> str:
        for k in keys:
            v = d.get(k)
            if v:
                return str(v)
        return ""

    cve = pick("VulnerabilityID", "vulnerability_id", "cve_id")
    if not cve and _ADVISORY_RE.match(finding.rule_id or ""):
        cve = finding.rule_id
    return {
        "pkg_name": pick("PkgName", "pkg_name", "package_name", "packageName", "component"),
        "installed_version": pick(
            "InstalledVersion", "installed_version", "current_version", "version",
        ),
        "fixed_version": pick(
            "FixedVersion", "fixed_version", "fix_version", "patchedVersions",
        ),
        "manifest_path": finding.file_path or pick("PkgPath", "Target", "manifest"),
        "cve_id": cve,
    }


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def verify_diff_grounding(
    remediation_diff: str | None, source_code: str | None,
) -> tuple[bool, str]:
    """Anti-hallucination check (V4.2): is the AI's fix diff anchored in the
    REAL source? Parse the diff's context/removed (non-`+`) lines and verify a
    meaningful share actually appear in the fetched file. A hallucinated fix
    (references code that isn't there) fails this check.

    Returns (grounded, note). No source to check against → not grounded
    (we won't claim a fix is verified when we can't verify it). A pure-addition
    diff has no anchor lines to disprove → treated as grounded (n/a).
    """
    if not source_code:
        return False, "không có mã nguồn để đối chiếu"
    if not remediation_diff:
        return False, "không có diff để kiểm"
    src_joined = _norm_ws(source_code)
    anchors: list[str] = []
    for raw in remediation_diff.splitlines():
        if raw.startswith(("+++", "---", "@@", "diff ", "index ")):
            continue
        if raw.startswith("+"):
            continue  # added lines aren't expected to exist in the source yet
        content = raw[1:] if raw[:1] in (" ", "-") else raw
        c = _norm_ws(content)
        if len(c) >= 4:  # skip trivial anchors like "}" / "):"
            anchors.append(c)
    if not anchors:
        return True, "diff chỉ thêm mới — không có dòng neo để kiểm"
    hits = sum(1 for a in anchors if a in src_joined)
    ratio = hits / len(anchors)
    if ratio >= 0.6:
        return True, f"diff khớp {hits}/{len(anchors)} dòng neo trong mã nguồn thật"
    return False, (
        f"diff chỉ khớp {hits}/{len(anchors)} dòng neo — có thể AI bịa mã không có thật"
    )


def _extract_context(source_code: str | None, line_number: int | None) -> str:
    if not source_code or not line_number:
        return ""
    lines = source_code.splitlines()
    start = max(0, line_number - 1 - _CONTEXT_LINES)
    end = min(len(lines), line_number + _CONTEXT_LINES)
    numbered = [f"{i + 1:4d} | {l}" for i, l in enumerate(lines[start:end], start=start)]
    return "\n".join(numbered)


# --- V4.3 investigation: wider context + evidence grounding -----------------
_WIDE_CONTEXT_LINES = 40      # ± window when a file is too big to send whole
_WHOLE_FILE_MAX_LINES = 400   # send the whole file (numbered) when this small


def _extract_wide_context(source_code: str | None, line_number: int | None) -> str:
    """Wider numbered context for data-flow reasoning: the WHOLE file when it is
    small enough, else ±_WIDE_CONTEXT_LINES around the finding line. Uses the
    same absolute 1-based numbering as `_extract_context` so the model's
    `line_start`/`line_end` citations map back to real file lines."""
    if not source_code:
        return ""
    lines = source_code.splitlines()
    if len(lines) <= _WHOLE_FILE_MAX_LINES:
        start, end = 0, len(lines)
    elif line_number:
        start = max(0, line_number - 1 - _WIDE_CONTEXT_LINES)
        end = min(len(lines), line_number + _WIDE_CONTEXT_LINES)
    else:
        start, end = 0, min(len(lines), 2 * _WIDE_CONTEXT_LINES)
    numbered = [f"{i + 1:4d} | {l}" for i, l in enumerate(lines[start:end], start=start)]
    return "\n".join(numbered)


def verify_investigation_grounding(steps, source_code: str | None):
    """V4.3 anti-hallucination for the investigation: verify each reasoning
    step's `quote` actually exists in the REAL source. Generalises
    `verify_diff_grounding` from diff-anchors to per-step code citations.

    `steps` = objects with `.quote`, `.line_start`, `.line_end` (InvestigationStep).
    Returns `(per_step[(grounded, note)], overall_grounded, overall_note)`, aligned
    with `steps`. Strong match = quote inside the cited line range; weak fallback
    = quote anywhere in the source (guards window/renumber drift). Steps that
    cite no real code (quote too short) are skipped from the ratio. Overall
    grounded when ≥60% of quoting steps match; no source or no citations at all
    → not grounded (we won't certify a verdict we can't back with real code).
    """
    lines = (source_code or "").splitlines()
    src_joined = _norm_ws(source_code or "")
    per_step: list[tuple[bool, str]] = []
    quoted = 0
    grounded_count = 0
    for st in steps:
        q = _norm_ws(getattr(st, "quote", "") or "")
        if len(q) < 4:
            per_step.append((True, "bước không trích dẫn code — bỏ qua kiểm neo"))
            continue
        quoted += 1
        if not src_joined:
            per_step.append((False, "không có mã nguồn để đối chiếu"))
            continue
        ls = int(getattr(st, "line_start", 0) or 0)
        le = int(getattr(st, "line_end", 0) or ls)
        window = _norm_ws("\n".join(lines[max(0, ls - 1):max(ls, le)])) if ls else ""
        if window and q in window:
            grounded_count += 1
            per_step.append((True, f"khớp dòng {ls}-{le or ls}"))
        elif q in src_joined:
            grounded_count += 1
            per_step.append((True, "khớp mã nguồn (lệch dòng trích dẫn)"))
        else:
            per_step.append((False, "trích dẫn không có trong mã nguồn — nghi bịa"))
    if quoted == 0:
        return per_step, False, "không có bước nào trích dẫn code để kiểm chứng"
    overall = grounded_count / quoted >= 0.6
    return per_step, overall, f"{grounded_count}/{quoted} bước có trích dẫn khớp mã nguồn thật"


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

    async def _resolve_clients(
        self, finding: Finding, session: AsyncSession,
    ) -> tuple[GeminiClient, GitHubClient, Project | None]:
        """Resolve per-project Gemini + GitHub clients (or the injected test
        doubles / env fallback). Shared by `_prepare_analysis` and
        `investigate_finding`. Returns `(gemini, github_client, project)`."""
        project = None
        if not self._injected_client or not self._injected_github:
            project = await self._resolve_project(finding, session)

        if self._injected_github is not None:
            github_client = self._injected_github
        elif project and project.github_owner and project.github_repo:
            # Bind to the PROJECT's repo (owner/repo) — fixes fetching a real
            # project's source from the wrong global default repo. Token: the
            # project's own when set, else fall back to the global .env token
            # (GitHubClient.__init__ does `token or settings.GITHUB_TOKEN`, so
            # for_project with an empty project token uses the default token).
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
        return gemini, github_client, project

    async def _ensure_source(
        self, finding: Finding, github_client: GitHubClient,
    ) -> str | None:
        """Return the finding's source: cached `raw_data['source_code']`, else a
        single best-effort GitHub fetch (scrubbed via L3, cached back onto the
        finding — caller commits). None when the path isn't a fetchable source
        file (unknown/binary) or the fetch fails. Shared by `_prepare_analysis`
        and `investigate_finding`."""
        source_code = (finding.raw_data or {}).get("source_code")
        if (
            not source_code
            and finding.file_path
            and finding.file_path not in ("unknown", "")
            and not finding.file_path.endswith((".jar", ".class", ".war", ".ear"))
        ):
            try:
                fetched = await github_client.fetch_file_content(finding.file_path)
                if fetched:
                    source_code = (
                        self._scrubber.scrub_content(fetched)
                        if layer_on("scrubbing") else fetched
                    )
                    raw = dict(finding.raw_data or {})
                    raw["source_code"] = source_code
                    finding.raw_data = raw
                    # caller's session.commit() persists the cache
            except Exception as exc:
                log.warning("Could not fetch source for finding %d: %s", finding.id, exc)
        return source_code

    async def _prepare_analysis(
        self,
        finding: Finding,
        session: AsyncSession,
    ) -> tuple[GeminiClient, str, str]:
        """Resolve per-project Gemini/GitHub clients, run the input guardrails,
        and render the prompt for a finding. Shared by `analyze_finding`
        (structured JSON output) and `stream_explain` (SSE streaming). Returns
        `(gemini, prompt, prompt_id)`. Raises ValueError if a guardrail blocks
        the content."""
        # B4 — resolve project credentials (tách ra _resolve_clients để dùng chung
        # với investigate_finding; hành vi không đổi).
        gemini, github_client, _project = await self._resolve_clients(finding, session)

        # CVE fix suggestion: lỗ hổng phụ thuộc (SCA) không sửa bằng code —
        # fix = nâng cấp phiên bản. Dùng prompt "cve" (gói + version) thay vì
        # "analyze" (vốn đòi unified diff sửa mã nguồn → vô nghĩa với CVE).
        prompt_id = "cve" if _is_dependency_finding(finding) else "analyze"

        # Layer 4 (injection) — chỉ áp khi GUARDRAIL_LAYERS bật "injection".
        # Tắt (GUARDRAIL_LAYERS=none) → bỏ qua, payload tới thẳng LLM (demo rủi ro).
        if layer_on("injection"):
            # Check the SANITIZED text (same bytes that reach the LLM): length is
            # bounded by sanitize(), so only real injection patterns can reject.
            safe_message, reason_msg = self._guardrail.check(
                self._guardrail.sanitize(finding.message or "")
            )
            if not safe_message:
                log.warning(
                    "Injection guardrail blocked finding %d: msg=%r", finding.id, reason_msg,
                )
                raise ValueError("Finding content rejected by injection guardrail")

        if prompt_id == "cve":
            meta = _dep_meta(finding)
            rendered = get_registry().render(
                "cve",
                tool_name=finding.tool,
                rule_id=finding.rule_id,
                message=self._guardrail.sanitize(finding.message or ""),
                cvss_score=finding.cvss_score,
                **meta,
            )
        else:
            source_code = await self._ensure_source(finding, github_client)

            code_context = _extract_context(source_code, finding.line_number)

            # Defend against indirect prompt injection: code context comes from
            # untrusted sources (open-source repos). Reject obvious injection.
            if layer_on("injection"):
                safe_context, reason_ctx = self._guardrail.check(
                    self._guardrail.sanitize(code_context)
                )
                if not safe_context:
                    log.warning(
                        "Injection guardrail blocked finding %d: ctx=%r", finding.id, reason_ctx,
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
        return gemini, prompt, prompt_id

    async def analyze_finding(
        self,
        finding: Finding,
        session: AsyncSession,
    ) -> AnalysisResult:
        gemini, prompt, prompt_id = await self._prepare_analysis(finding, session)

        output: AnalysisOutput = await gemini.analyze(prompt, system_prompt_id=prompt_id)

        result = AnalysisResult(
            finding_id=finding.id,
            vulnerability_id=output.vulnerability_id,
            explanation_vi=output.explanation_vi,
            impact_vi=output.impact_vi,
            remediation_diff=output.remediation_diff,
            severity=output.severity,
            cwe_reference=output.cwe_reference,
            confidence=output.confidence,
            false_positive_likelihood=output.false_positive_likelihood,
            false_positive_reason=output.false_positive_reason,
        )

        # V4.2 anti-hallucination — verify the fix diff is anchored in the real
        # code (SAST/analyze only; CVE remediation is a manifest version bump).
        # An ungrounded fix is downgraded to LOW confidence and flagged so the
        # dashboard warns instead of presenting hallucinated code as authoritative.
        if prompt_id == "analyze":
            src = (finding.raw_data or {}).get("source_code")
            grounded, note = verify_diff_grounding(output.remediation_diff, src)
            result.grounded = grounded
            result.grounded_note = note
            if not grounded:
                result.confidence = "LOW"

        finding.status = "ai_analyzed"
        finding.ai_analysis = result.model_dump()
        await session.commit()

        log.info("finding %d analyzed by Gemini (confidence=%s)", finding.id, output.confidence)
        return result

    async def stream_explain(
        self,
        finding: Finding,
        session: AsyncSession,
    ) -> AsyncIterator[str]:
        """Stream the Vietnamese explanation for a finding chunk-by-chunk
        (SSE backend for GET /findings/{id}/explain/stream, report §4.3.4).

        If the finding was already analyzed, the cached explanation is replayed
        as a single chunk (no second LLM call). Otherwise the prompt is built
        exactly like `analyze_finding` and streamed via `GeminiClient.
        stream_analyze`. This path streams the prose only; the structured
        AnalysisResult (with remediation_diff etc.) stays with the POST endpoint,
        so no partial/degraded result is written to the cache here."""
        if finding.status == "ai_analyzed" and finding.ai_analysis:
            cached = finding.ai_analysis.get("explanation_vi") or ""
            if cached:
                yield cached
            return

        gemini, prompt, prompt_id = await self._prepare_analysis(finding, session)
        async for chunk in gemini.stream_analyze(prompt, system_prompt_id=prompt_id):
            yield chunk

    # ------------------------------------------------------------------
    # V4.3 — "lỗi này có thật không?" investigation (data-flow + evidence)
    # ------------------------------------------------------------------

    async def investigate_finding(
        self,
        finding: Finding,
        session: AsyncSession,
        force: bool = False,
    ) -> FPInvestigation:
        """Trace the finding's LOCAL data flow over the real source and decide
        TRUE_POSITIVE / FALSE_POSITIVE / UNCERTAIN, returning a step-by-step
        reasoning trace where every step cites real code (line range + quote).

        Advisory only — NEVER mutates `finding.status` / `finding.ai_analysis`;
        the result is cached under `raw_data['fp_investigation']`. Every FP
        verdict must be backed by grounded evidence, else it is downgraded to
        UNCERTAIN (anti-hallucination). No source / dependency finding → UNCERTAIN
        (never a metadata-only FP)."""
        cached = (finding.raw_data or {}).get("fp_investigation")
        if cached and not force:
            try:
                return FPInvestigation.model_validate(cached)
            except Exception:  # stale/legacy shape → recompute
                pass

        gemini, github_client, _project = await self._resolve_clients(finding, session)

        # Dependency/CVE: fix = nâng version, không phải luồng mã → UNCERTAIN + hướng dẫn.
        if _is_dependency_finding(finding):
            meta = _dep_meta(finding)
            summary = (
                f"Đây là lỗ hổng phụ thuộc ({meta.get('cve_id') or finding.rule_id}) tại "
                f"{meta.get('pkg_name') or finding.file_path or '?'}. Không phải luồng dữ liệu "
                f"trong mã — cần đối chiếu phiên bản đang dùng "
                f"({meta.get('installed_version') or '?'}) với bản vá "
                f"({meta.get('fixed_version') or '?'}). Dùng /explain để xem hướng nâng cấp."
            )
            result = FPInvestigation(
                finding_id=finding.id, verdict="UNCERTAIN", confidence="LOW",
                summary_vi=summary, steps=[], false_positive_likelihood="LOW",
                grounded=True, grounded_note="lỗ hổng phụ thuộc — không kiểm luồng mã",
                source_available=False, suggested_command=None,
            )
            return await self._persist_investigation(finding, session, result)

        source_code = await self._ensure_source(finding, github_client)
        if not source_code:
            result = FPInvestigation(
                finding_id=finding.id, verdict="UNCERTAIN", confidence="LOW",
                summary_vi=("Không đủ mã nguồn để kết luận — không lấy được file nguồn "
                            "của finding này (thiếu token/không phải file mã). Cần người xem xét."),
                steps=[], false_positive_likelihood="LOW",
                grounded=False, grounded_note="không có mã nguồn để đối chiếu",
                source_available=False, suggested_command=None,
            )
            return await self._persist_investigation(finding, session, result)

        code_context = _extract_wide_context(source_code, finding.line_number)

        if layer_on("injection"):
            # Check the SANITIZED text (what actually reaches the LLM): the wide
            # investigation context is legitimately large, so length must not
            # reject — only genuine injection patterns should.
            safe_msg, _ = self._guardrail.check(self._guardrail.sanitize(finding.message or ""))
            safe_ctx, _ = self._guardrail.check(self._guardrail.sanitize(code_context))
            if not (safe_msg and safe_ctx):
                log.warning("Injection guardrail blocked investigation for finding %d", finding.id)
                raise ValueError("Finding content rejected by injection guardrail")

        rendered = get_registry().render(
            "investigate",
            tool_name=finding.tool,
            rule_id=finding.rule_id,
            message=self._guardrail.sanitize(finding.message or ""),
            file_path=finding.file_path,
            line_number=finding.line_number,
            cwe_id=finding.cwe_id,
            cvss_score=finding.cvss_score,
            code_context=self._guardrail.sanitize(code_context),
        )
        output = await gemini.investigate(rendered.user or "")

        steps = [
            InvestigationStep(
                claim_vi=s.claim_vi,
                kind=s.kind,
                file=s.code_ref.file or finding.file_path or "",
                line_start=s.code_ref.line_start,
                line_end=s.code_ref.line_end or s.code_ref.line_start,
                quote=s.quote,
            )
            for s in output.reasoning_steps
        ]

        # Ground each step's citation against the FULL fetched source.
        per_step, overall, note = verify_investigation_grounding(steps, source_code)
        for st, (g, gn) in zip(steps, per_step):
            st.grounded = g
            st.grounded_note = gn

        verdict = output.verdict
        confidence = output.confidence
        fpl = output.false_positive_likelihood
        grounded_note = note
        # Anti-hallucination: a FALSE_POSITIVE claim must be backed by grounded
        # evidence — otherwise never present it as FP (downgrade to UNCERTAIN).
        if verdict == "FALSE_POSITIVE" and not overall:
            verdict = "UNCERTAIN"
            confidence = "LOW"
            fpl = "MEDIUM"
            grounded_note = note + " — hạ về UNCERTAIN vì bằng chứng chưa neo được vào mã thật"

        suggested = None
        if verdict == "FALSE_POSITIVE":
            suggested = f"/revoke {finding.id}"
        elif verdict == "TRUE_POSITIVE":
            suggested = f"/fix {finding.id}"

        result = FPInvestigation(
            finding_id=finding.id, verdict=verdict, confidence=confidence,
            summary_vi=output.summary_vi, steps=steps, false_positive_likelihood=fpl,
            grounded=overall, grounded_note=grounded_note,
            source_available=True, suggested_command=suggested,
        )
        return await self._persist_investigation(finding, session, result)

    async def _persist_investigation(
        self, finding: Finding, session: AsyncSession, result: FPInvestigation,
    ) -> FPInvestigation:
        """Cache the investigation on raw_data (advisory-only; no status change)."""
        raw = dict(finding.raw_data or {})
        raw["fp_investigation"] = result.model_dump()
        finding.raw_data = raw
        await session.commit()
        log.info(
            "finding %d investigated: verdict=%s grounded=%s",
            finding.id, result.verdict, result.grounded,
        )
        return result

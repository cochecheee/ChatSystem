from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..core.db import AsyncSessionLocal
from ..core.profiles import ArtifactProfile, load_profile
from ..models.entities import Artifact, Finding
from ..models.schemas import compute_dedup_hash
from .enricher import DataEnricher
from .github_client import GitHubClient
from ..core.guardrails import ScrubbingService
from .normalizer import NormalizerFactory

log = logging.getLogger(__name__)


def _is_security_artifact(name: str, profile: ArtifactProfile | None = None) -> bool:
    """Check whether a workflow artifact name matches the configured profile.

    The profile is loaded once per process (LRU-cached). Passing an explicit
    profile is intended for Day 2 (per-`Project` profile lookup).
    """
    return (profile or load_profile()).matches(name)


class SecurityProcessor:
    """Orchestrates the full pipeline: fetch → scrub → normalize → enrich → store."""

    def __init__(
        self,
        session_factory: async_sessionmaker | None = None,
        github_client: GitHubClient | None = None,
        scrubber: ScrubbingService | None = None,
        enricher: DataEnricher | None = None,
    ) -> None:
        self.session_factory = session_factory or AsyncSessionLocal
        self.github_client = github_client or GitHubClient()
        self.scrubber = scrubber or ScrubbingService()
        self.enricher = enricher or DataEnricher()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_artifact(
        self,
        db_artifact_id: int,
        github_artifact_id: int,
        gh: GitHubClient | None = None,
    ) -> int:
        """Fetch, scrub, normalize, enrich, and store findings for one artifact.

        Returns the number of findings stored. Pass `gh` to use a
        per-project client (Day 2 multi-tenant); omitted falls back to
        the default singleton.
        """
        async with self.session_factory() as session:
            return await self._run(session, db_artifact_id, github_artifact_id, gh)

    async def process_run(
        self,
        project_id: int,
        github_run_id: int,
        project=None,
    ) -> None:
        """Fetch security artifacts from a GitHub workflow run and process each one.

        Routing (V2.8 B2):
          - Background task được spawn từ webhook handler chỉ pass project_id
            (tránh detached ORM instance khi request session closed). Method
            tự fetch Project bằng id và xây per-project GitHubClient nếu có
            credentials.
          - Poller flow có thể pass `project` ORM object trực tiếp (đang
            trong session) — short-circuit lookup.
          - Project thiếu credentials (github_token/owner/repo trống) →
            fallback `self.github_client` (env-bound, single-tenant).
        """
        from ..models.entities import Artifact as ArtifactModel
        from ..models.entities import Project as ProjectModel

        if project is None:
            async with self.session_factory() as session:
                project = await session.get(ProjectModel, project_id)
                # Detach để dùng ngoài session (read-only access vào field)
                if project is not None:
                    session.expunge(project)

        if project is not None and project.github_token and project.github_owner and project.github_repo:
            gh = GitHubClient.for_project(project)
            profile = load_profile(project.artifact_profile or None)
            log.info(
                "process_run %d: using per-project credentials for %s/%s",
                github_run_id, project.github_owner, project.github_repo,
            )
        else:
            gh = self.github_client
            profile = load_profile()
            log.info(
                "process_run %d: using env-bound GitHub client (no per-project credentials)",
                github_run_id,
            )

        all_artifacts = await gh.list_artifacts(github_run_id)
        security_artifacts = [
            a for a in all_artifacts if _is_security_artifact(a.get("name", ""), profile)
        ]
        log.info(
            "Run %d: %d/%d artifacts are security-relevant",
            github_run_id, len(security_artifacts), len(all_artifacts),
        )

        processed_count = 0
        failed_count = 0
        for gh_artifact in security_artifacts:
            gh_artifact_id = str(gh_artifact["id"])
            async with self.session_factory() as session:
                # Idempotency: SAST and DAST webhooks land separately but
                # both call process_run with the same run_id; list_artifacts
                # returns the cumulative set on each call, so without this
                # check we'd recreate Artifact rows + duplicate Findings on
                # every overlapping webhook (or workflow rerun).
                existing = await session.execute(
                    select(ArtifactModel).where(
                        ArtifactModel.project_id == project_id,
                        ArtifactModel.github_artifact_id == gh_artifact_id,
                    )
                )
                db_artifact = existing.scalar_one_or_none()
                if db_artifact is not None and db_artifact.status == "processed":
                    log.info(
                        "Skipping artifact %s — already processed (db_id=%d)",
                        gh_artifact_id, db_artifact.id,
                    )
                    continue
                if db_artifact is None:
                    db_artifact = ArtifactModel(
                        github_artifact_id=gh_artifact_id,
                        project_id=project_id,
                        github_run_id=github_run_id,
                        status="pending",
                    )
                    session.add(db_artifact)
                    await session.commit()
                    await session.refresh(db_artifact)
                else:
                    # BUG-5 fix — artifact row exists but isn't 'processed'
                    # (status='pending' or 'failed' from a crashed prior run).
                    # Re-running _run on it would APPEND findings on top of the
                    # half-written set, producing duplicates. Wipe its findings
                    # first so the next pass is a clean re-ingest.
                    from ..models.entities import Finding as FindingModel
                    from sqlalchemy import delete as _sql_delete
                    await session.execute(
                        _sql_delete(FindingModel).where(
                            FindingModel.artifact_id == db_artifact.id,
                        )
                    )
                    await session.commit()
                    log.info(
                        "Cleaning stale findings for artifact %s (db_id=%d, status=%s) before retry",
                        gh_artifact_id, db_artifact.id, db_artifact.status,
                    )

            # BUG-4 fix — isolate per-artifact failures. One broken zip or a
            # normalizer crash on a single SARIF file must not stop the rest
            # of the run. Log + count, then continue.
            try:
                await self.process_artifact(db_artifact.id, gh_artifact["id"], gh=gh)
                processed_count += 1
            except Exception as exc:
                failed_count += 1
                log.error(
                    "process_run %d: artifact %s crashed — %s. Continuing with rest of run.",
                    github_run_id, gh_artifact_id, exc,
                )

        # BUG-1 fix — webhook path also bumps last_processed_run_id so the UI
        # and /projects API reflect the most recent ingest. Previously only
        # the poller did this, so webhook-driven runs left the field at None.
        # Only advance forward (never rewrite older run as latest).
        if processed_count > 0:
            async with self.session_factory() as session:
                db_proj = await session.get(ProjectModel, project_id)
                if db_proj is not None:
                    current = db_proj.last_processed_run_id or 0
                    if github_run_id > current:
                        db_proj.last_processed_run_id = github_run_id
                        await session.commit()

        log.info(
            "process_run %d done — %d processed, %d failed (out of %d security artifacts)",
            github_run_id, processed_count, failed_count, len(security_artifacts),
        )

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    async def _run(
        self,
        session: AsyncSession,
        db_artifact_id: int,
        github_artifact_id: int,
        gh: GitHubClient | None = None,
    ) -> int:
        artifact = await session.get(Artifact, db_artifact_id)
        if artifact is None:
            raise ValueError(f"Artifact {db_artifact_id} not found in database")

        client = gh or self.github_client
        try:
            files = await client.fetch_artifact(github_artifact_id)
            db_findings = self._build_findings(files, db_artifact_id)

            # V3.1 Tier 1 — cross-run auto-revoke by dedup_hash match.
            # V3.1 Tier 2 — pattern-based auto-revoke from suppression_rules.
            # Tier 1 wins when both match (more specific = exact hash).
            from ..repositories.finding_repo import FindingRepository
            from ..repositories.suppression_repo import (
                SuppressionRuleRepository, rule_matches,
            )
            repo = FindingRepository(session)
            sup_repo = SuppressionRuleRepository(session)
            hashes = {f.dedup_hash for f in db_findings if f.dedup_hash}
            project_id = artifact.project_id
            prior = await repo.find_revoked_hashes(hashes, project_id=project_id)
            active_rules = await sup_repo.list_active_for_project(project_id)
            auto_count_t1 = 0
            auto_count_t2 = 0
            for f in db_findings:
                if f.dedup_hash and f.dedup_hash in prior:
                    p = prior[f.dedup_hash]
                    f.status = "REVOKED"
                    f.revoked_by = "auto-suppress"
                    f.revoke_justification = (
                        f"Auto-suppressed (V3.1 Tier 1): inherited revoke from "
                        f"{p['revoked_by']!r} — {p['revoke_justification']}"
                    )
                    f.revoked_at = datetime.now(UTC)
                    auto_count_t1 += 1
                    continue
                for rule in active_rules:
                    if rule_matches(
                        rule,
                        finding_rule_id=f.rule_id,
                        finding_file_path=f.file_path,
                        finding_tool=f.tool,
                        finding_severity=f.severity,
                    ):
                        f.status = "REVOKED"
                        f.revoked_by = f"auto-suppress (rule #{rule.id})"
                        f.revoke_justification = (
                            f"Auto-suppressed (V3.1 Tier 2 rule #{rule.id} by "
                            f"{rule.created_by}): {rule.reason}"
                        )
                        f.revoked_at = datetime.now(UTC)
                        auto_count_t2 += 1
                        break
            auto_count = auto_count_t1 + auto_count_t2

            session.add_all(db_findings)
            artifact.status = "processed"
            await session.commit()

            log.info(
                "Stored %d findings for artifact %d (auto-revoked %d: %d by dedup_hash, %d by rule)",
                len(db_findings), db_artifact_id, auto_count, auto_count_t1, auto_count_t2,
            )
            return len(db_findings)

        except Exception as exc:
            artifact.status = "failed"
            await session.commit()
            log.error("Failed to process artifact %d: %s", db_artifact_id, exc)
            raise

    def _build_findings(
        self,
        files: list[dict[str, str]],
        db_artifact_id: int,
    ) -> list[Finding]:
        batch_hashes: set[str] = set()
        results: list[Finding] = []

        for file_info in files:
            filename = file_info["filename"]
            scrubbed = self.scrubber.scrub_content(file_info["content"])

            try:
                normalizer = NormalizerFactory.get(filename, content=scrubbed)
            except ValueError as exc:
                log.info("Skipping %s — %s", filename, exc)
                continue

            try:
                findings = normalizer.normalize(scrubbed, artifact_id=db_artifact_id)
            except Exception as exc:  # noqa: BLE001 - isolate per-file parse errors
                log.warning("Failed to normalize %s: %s — skipping this file", filename, exc)
                continue

            log.info(
                "%s: %d findings normalized by %s",
                filename, len(findings), type(normalizer).__name__,
            )

            findings = normalizer.deduplicate(findings, existing_hashes=batch_hashes)

            for schema_finding in findings:
                enriched = self.enricher.enrich(schema_finding)
                # V2.7 — scrub PII trên message POST-parse. scrub_content
                # pre-parse từng break JSON escape (Issue: codeql.sarif silent
                # drop). Per-field scrub đảm bảo email/IP không lọt vào DB +
                # JSON SARIF vẫn parse được.
                scrubbed_message = self.scrubber.scrub_text(enriched.message)
                h = compute_dedup_hash(
                    enriched.rule_id, enriched.file_path, scrubbed_message
                )
                batch_hashes.add(h)

                results.append(
                    Finding(
                        artifact_id=db_artifact_id,
                        tool=enriched.tool,
                        rule_id=enriched.rule_id,
                        severity=enriched.severity,
                        message=scrubbed_message,
                        file_path=enriched.file_path,
                        line_number=enriched.line_number,
                        raw_data=enriched.raw_data,
                        cwe_id=enriched.cwe_id,
                        cvss_score=enriched.cvss_score,
                        dedup_hash=h,
                        normalized_at=datetime.now(UTC),
                    )
                )

        return results

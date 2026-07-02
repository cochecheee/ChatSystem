from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, func as sql_func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..core.db import AsyncSessionLocal
from ..core.guardrails import ScrubbingService
from ..core.profiles import ArtifactProfile, load_profile
from ..models.entities import Artifact, Finding
from ..models.schemas import compute_dedup_hash
from .enricher import DataEnricher
from .github_client import GitHubClient
from .normalizers import NormalizerFactory

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

        # Route to the project's OWN repo whenever owner+repo are known — a
        # per-project token is NOT required. GitHubClient.for_project falls
        # back to the env GITHUB_TOKEN for auth (public repos work even
        # unauthenticated), so keying on github_token here was a bug: a
        # tokenless multi-tenant project (e.g. a public repo) silently fell
        # back to the ENV repo and fetched the WRONG run → 404 → 0 findings
        # (which wiped that project's data on reprocess).
        if project is not None and project.github_owner and project.github_repo:
            gh = GitHubClient.for_project(project)
            profile = load_profile(project.artifact_profile or None)
            log.info(
                "process_run %d: using repo %s/%s (token=%s)",
                github_run_id, project.github_owner, project.github_repo,
                "per-project" if project.github_token else "env-fallback",
            )
        else:
            gh = self.github_client
            profile = load_profile()
            log.info(
                "process_run %d: using env-bound GitHub client (project has no owner/repo)",
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
                    from sqlalchemy import delete as _sql_delete

                    from ..models.entities import Finding as FindingModel
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

        # V3.8 Option A — current-state storage. After ingesting the newest
        # run, drop findings from OLDER runs of this project so the DB holds
        # only the latest scan per project (no per-run duplication → stored
        # data, dashboard KPIs, and the Vulns/SCA/DAST lists all agree at the
        # source, not just via query-time latest_run_only scoping). Guarded to
        # skip when reprocessing an OLD run so we never wipe newer data.
        if processed_count > 0:
            await self._prune_superseded_findings(project_id, github_run_id)

        log.info(
            "process_run %d done — %d processed, %d failed (out of %d security artifacts)",
            github_run_id, processed_count, failed_count, len(security_artifacts),
        )

    async def _prune_superseded_findings(
        self, project_id: int, keep_github_run_id: int,
    ) -> int:
        """Delete findings belonging to runs OLDER than keep_github_run_id for
        this project — current-state storage (V3.8 Option A).

        Guard: only prune when keep_github_run_id is the newest run for the
        project (GitHub run ids increase monotonically). Reprocessing an old
        run must NOT delete the newer run's findings.

        Keeps Artifact + PipelineRun rows (run metadata / history) intact —
        only the duplicated Finding rows (and any CommandFeedback pointing at
        them) are removed. Returns the number of findings deleted.
        """
        from ..models.entities import Artifact as ArtifactModel
        from ..models.entities import CommandFeedback as FeedbackModel
        from ..models.entities import Finding as FindingModel

        async with self.session_factory() as session:
            newest = (await session.execute(
                select(sql_func.max(ArtifactModel.github_run_id)).where(
                    ArtifactModel.project_id == project_id,
                    ArtifactModel.github_run_id.is_not(None),
                )
            )).scalar_one_or_none() or 0
            if keep_github_run_id < newest:
                log.info(
                    "Prune skipped: run %d is older than newest %d for project %d",
                    keep_github_run_id, newest, project_id,
                )
                return 0

            old_artifact_ids = [
                r[0] for r in (await session.execute(
                    select(ArtifactModel.id).where(
                        ArtifactModel.project_id == project_id,
                        ArtifactModel.github_run_id.is_not(None),
                        ArtifactModel.github_run_id != keep_github_run_id,
                    )
                )).all()
            ]
            if not old_artifact_ids:
                return 0

            old_finding_ids = [
                r[0] for r in (await session.execute(
                    select(FindingModel.id).where(
                        FindingModel.artifact_id.in_(old_artifact_ids)
                    )
                )).all()
            ]
            if not old_finding_ids:
                return 0

            # FK order: feedback (finding_id, no cascade) → findings.
            await session.execute(
                delete(FeedbackModel).where(
                    FeedbackModel.finding_id.in_(old_finding_ids)
                )
            )
            result = await session.execute(
                delete(FindingModel).where(
                    FindingModel.id.in_(old_finding_ids)
                )
            )
            await session.commit()
            deleted = result.rowcount or len(old_finding_ids)
            log.info(
                "Pruned %d superseded findings from %d older-run artifact(s) "
                "(project %d, kept run %d)",
                deleted, len(old_artifact_ids), project_id, keep_github_run_id,
            )
            return deleted

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
            db_findings = self._build_findings(files, db_artifact_id, artifact.project_id)

            # V3.1 Tier 1 — cross-run auto-revoke by dedup_hash match.
            # V3.1 Tier 2 — pattern-based auto-revoke from suppression_rules.
            # Tier 1 wins when both match (more specific = exact hash).
            from ..repositories.finding_repo import FindingRepository
            from ..repositories.suppression_repo import (
                SuppressionRuleRepository,
                rule_matches,
            )
            repo = FindingRepository(session)
            sup_repo = SuppressionRuleRepository(session)
            hashes = {f.dedup_hash for f in db_findings if f.dedup_hash}
            project_id = artifact.project_id
            prior = await repo.find_revoked_hashes(hashes, project_id=project_id)
            prior_appr = await repo.find_approved_hashes(hashes, project_id=project_id)
            active_rules = await sup_repo.list_active_for_project(project_id)
            auto_count_t1 = 0
            auto_count_t2 = 0
            auto_count_appr = 0
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
                # Tier 1 (approve) — carry forward an accepted-risk APPROVE so
                # the gate does NOT re-flag it next run. §5.2.5 / §4.2.3.
                if f.dedup_hash and f.dedup_hash in prior_appr:
                    p = prior_appr[f.dedup_hash]
                    f.status = "APPROVED"
                    f.approved_by = p["approved_by"] or "auto-approve"
                    f.justification = (
                        f"Auto-carried approval (V3.1 Tier 1): inherited APPROVE "
                        f"from {p['approved_by']!r} — {p['justification']}"
                    )
                    f.approved_at = datetime.now(UTC)
                    auto_count_appr += 1
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
            auto_count = auto_count_t1 + auto_count_t2 + auto_count_appr

            session.add_all(db_findings)
            await session.flush()  # assign finding PKs before writing audit rows

            # §4.3.3 audit trail — the CI/CD pipeline (webhook → process_run) is
            # a state-changing source. Every auto-carried REVOKE/APPROVE decision
            # is recorded in finding_actions with submitted_by=webhook:<token-id>
            # so pipeline-driven triage is distinguishable from dashboard:/mcp:
            # actions in the immutable audit log.
            from ..models.entities import FindingAction
            for f in db_findings:
                if f.status == "REVOKED" and str(f.revoked_by or "").startswith("auto-suppress"):
                    session.add(FindingAction(
                        finding_id=f.id, action="revoke",
                        submitted_by="webhook:auto-triage",
                        detail=(f.revoke_justification or "")[:1000],
                    ))
                elif f.status == "APPROVED" and (f.justification or "").startswith("Auto-carried approval"):
                    session.add(FindingAction(
                        finding_id=f.id, action="approve",
                        submitted_by="webhook:auto-triage",
                        detail=(f.justification or "")[:1000],
                    ))

            artifact.status = "processed"
            await session.commit()

            log.info(
                "Stored %d findings for artifact %d (auto-triaged %d: %d revoke-hash, %d rule, %d approve-hash)",
                len(db_findings), db_artifact_id, auto_count, auto_count_t1, auto_count_t2, auto_count_appr,
            )
            return len(db_findings)

        except Exception as exc:
            # Transactional ingest — any failure mid-pipeline (fetch, normalize,
            # or the findings commit itself) rolls the whole unit of work back so
            # NO half-written findings are persisted. Then mark the artifact
            # 'failed' in a fresh, clean transaction. Without the rollback, a
            # failure during commit() could leave the session in a poisoned
            # state and the subsequent status write would raise (or worse,
            # partially commit).
            await session.rollback()
            stale = await session.get(Artifact, db_artifact_id)
            if stale is not None:
                stale.status = "failed"
                await session.commit()
            log.error("Failed to process artifact %d: %s", db_artifact_id, exc)
            raise

    def _build_findings(
        self,
        files: list[dict[str, str]],
        db_artifact_id: int,
        project_id: int | None = None,
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
            except Exception as exc:
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
                        project_id=project_id,
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

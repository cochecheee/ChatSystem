from __future__ import annotations

import logging
from datetime import UTC, datetime

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
    ) -> int:
        """Fetch, scrub, normalize, enrich, and store findings for one artifact.

        Returns the number of findings stored.
        """
        async with self.session_factory() as session:
            return await self._run(session, db_artifact_id, github_artifact_id)

    async def process_run(self, project_id: int, github_run_id: int) -> None:
        """Fetch security artifacts from a GitHub workflow run and process each one."""
        from ..models.entities import Artifact as ArtifactModel

        all_artifacts = await self.github_client.list_artifacts(github_run_id)
        profile = load_profile()
        security_artifacts = [
            a for a in all_artifacts if _is_security_artifact(a.get("name", ""), profile)
        ]
        log.info(
            "Run %d: %d/%d artifacts are security-relevant",
            github_run_id, len(security_artifacts), len(all_artifacts),
        )

        for gh_artifact in security_artifacts:
            async with self.session_factory() as session:
                db_artifact = ArtifactModel(
                    github_artifact_id=str(gh_artifact["id"]),
                    project_id=project_id,
                    github_run_id=github_run_id,
                    status="pending",
                )
                session.add(db_artifact)
                await session.commit()
                await session.refresh(db_artifact)

            await self.process_artifact(db_artifact.id, gh_artifact["id"])

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    async def _run(
        self,
        session: AsyncSession,
        db_artifact_id: int,
        github_artifact_id: int,
    ) -> int:
        artifact = await session.get(Artifact, db_artifact_id)
        if artifact is None:
            raise ValueError(f"Artifact {db_artifact_id} not found in database")

        try:
            files = await self.github_client.fetch_artifact(github_artifact_id)
            db_findings = self._build_findings(files, db_artifact_id)

            session.add_all(db_findings)
            artifact.status = "processed"
            await session.commit()

            log.info("Stored %d findings for artifact %d", len(db_findings), db_artifact_id)
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
                h = compute_dedup_hash(
                    enriched.rule_id, enriched.file_path, enriched.message
                )
                batch_hashes.add(h)

                results.append(
                    Finding(
                        artifact_id=db_artifact_id,
                        tool=enriched.tool,
                        rule_id=enriched.rule_id,
                        severity=enriched.severity,
                        message=enriched.message,
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

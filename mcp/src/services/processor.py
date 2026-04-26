from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..core.db import AsyncSessionLocal
from ..models.entities import Artifact, Finding
from ..models.schemas import compute_dedup_hash
from .enricher import DataEnricher
from .github_client import GitHubClient
from ..core.guardrails import ScrubbingService
from .normalizer import NormalizerFactory

log = logging.getLogger(__name__)

# Artifact names produced by the SAST_CICD pipeline that contain security findings.
# Other artifacts (gate1-result-*, run-metadata-*, build-classes, trivy-image-scan-*)
# are metadata/build artifacts and must not be processed as security findings.
_SECURITY_ARTIFACT_NAMES = frozenset({
    "spotbugs-report",
    "semgrep-report",
    "codeql-report",
    "dep-check-report",
    "trivy-report",
    "eslint-report",
})


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
        security_artifacts = [
            a for a in all_artifacts if a.get("name") in _SECURITY_ARTIFACT_NAMES
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
            scrubbed = self.scrubber.scrub_content(file_info["content"])

            try:
                # Pass scrubbed content so the factory can detect JSON format
                normalizer = NormalizerFactory.get(file_info["filename"], content=scrubbed)
            except ValueError:
                log.debug("No normalizer for %s — skipping", file_info["filename"])
                continue

            findings = normalizer.normalize(scrubbed, artifact_id=db_artifact_id)
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

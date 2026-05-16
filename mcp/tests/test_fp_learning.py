"""V3.1 Tier 1 — cross-run auto-revoke tests.

When a finding's dedup_hash matches a prior REVOKED row on the same project,
new ingest should automatically inherit the REVOKED status with a clear
audit trail. This is the foundational learning loop: dev revokes once,
system suppresses forever (until they re-approve or the hash changes).
"""
import io
import json
import zipfile
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.db import Base
from src.models.entities import Artifact, Finding, Project
from src.services.processor import SecurityProcessor


@pytest.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


SAMPLE_SARIF = {
    "version": "2.1.0",
    "runs": [{"tool": {"driver": {"name": "Semgrep"}},
              "results": [{
                  "ruleId": "python.lang.security.exec-use",
                  "level": "error",
                  "message": {"text": "Use of exec()"},
                  "locations": [{"physicalLocation": {
                      "artifactLocation": {"uri": "src/app.py"},
                      "region": {"startLine": 42}}}],
              }]}],
}


async def _create_project_and_artifact(db, github_artifact_id: str = "999") -> tuple[int, int]:
    async with db() as session:
        project = Project(name="P", github_url="https://github.com/test/p")
        session.add(project)
        await session.commit()
        await session.refresh(project)

        artifact = Artifact(
            github_artifact_id=github_artifact_id,
            project_id=project.id,
            status="pending",
        )
        session.add(artifact)
        await session.commit()
        await session.refresh(artifact)
        return project.id, artifact.id


async def _ingest(db, artifact_id: int) -> int:
    """Run the processor against a fixed SARIF blob — returns finding count."""
    mock_github = AsyncMock()
    mock_github.fetch_artifact.return_value = [
        {"filename": "results.sarif", "content": json.dumps(SAMPLE_SARIF)}
    ]
    processor = SecurityProcessor(session_factory=db, github_client=mock_github)
    return await processor.process_artifact(artifact_id, github_artifact_id=999)


@pytest.mark.asyncio
async def test_first_run_findings_are_pending(db):
    """Baseline: with no prior REVOKED row, ingest produces pending_review."""
    _, artifact_id = await _create_project_and_artifact(db)
    count = await _ingest(db, artifact_id)
    assert count == 1

    async with db() as session:
        f = (await session.execute(select(Finding))).scalar_one()
        assert f.status == "pending_review"
        assert f.revoked_by is None


@pytest.mark.asyncio
async def test_second_run_inherits_revoked_status(db):
    """Revoke a finding on run 1, ingest the same finding on run 2 (different
    artifact) — V3.1 should auto-mark the new row REVOKED."""
    project_id, artifact1 = await _create_project_and_artifact(db, "art-1")
    await _ingest(db, artifact1)

    # Human revokes the run-1 finding
    async with db() as session:
        f1 = (await session.execute(select(Finding))).scalar_one()
        f1.status = "REVOKED"
        f1.revoked_by = "alice"
        f1.revoke_justification = "Intended use of exec — not a vulnerability"
        from datetime import datetime, UTC
        f1.revoked_at = datetime.now(UTC)
        await session.commit()
        original_hash = f1.dedup_hash

    # Same project, NEW artifact ingests the same finding (run 2)
    async with db() as session:
        artifact2 = Artifact(
            github_artifact_id="art-2", project_id=project_id, status="pending",
        )
        session.add(artifact2)
        await session.commit()
        await session.refresh(artifact2)
        artifact2_id = artifact2.id

    await _ingest(db, artifact2_id)

    async with db() as session:
        all_findings = (await session.execute(select(Finding).order_by(Finding.id))).scalars().all()
        assert len(all_findings) == 2
        new = all_findings[1]
        assert new.dedup_hash == original_hash
        assert new.status == "REVOKED"
        assert new.revoked_by == "auto-suppress"
        assert "inherited revoke from 'alice'" in new.revoke_justification
        assert "Intended use of exec" in new.revoke_justification


@pytest.mark.asyncio
async def test_revoke_does_not_cross_projects(db):
    """Same dedup_hash on a different project must NOT inherit revoke —
    each repo is its own decision domain."""
    project1_id, artifact1 = await _create_project_and_artifact(db, "p1-a1")
    await _ingest(db, artifact1)
    async with db() as session:
        f = (await session.execute(select(Finding))).scalar_one()
        f.status = "REVOKED"
        f.revoked_by = "alice"
        f.revoke_justification = "FP on project 1"
        from datetime import datetime, UTC
        f.revoked_at = datetime.now(UTC)
        await session.commit()

    # New project, new artifact
    async with db() as session:
        project2 = Project(name="P2", github_url="https://github.com/test/other")
        session.add(project2)
        await session.commit()
        await session.refresh(project2)
        artifact2 = Artifact(
            github_artifact_id="p2-a1", project_id=project2.id, status="pending",
        )
        session.add(artifact2)
        await session.commit()
        await session.refresh(artifact2)
        artifact2_id = artifact2.id

    await _ingest(db, artifact2_id)

    async with db() as session:
        new = (
            await session.execute(
                select(Finding).join(Artifact).where(Artifact.project_id == project2.id)
            )
        ).scalar_one()
        # Cross-project: hash matches but project differs → no auto-revoke
        assert new.status == "pending_review"
        assert new.revoked_by is None


@pytest.mark.asyncio
async def test_no_prior_revokes_no_change(db):
    """Smoke check: when nothing is revoked anywhere, ingest is a no-op for the loop."""
    _, artifact_id = await _create_project_and_artifact(db)
    await _ingest(db, artifact_id)

    async with db() as session:
        all_findings = (await session.execute(select(Finding))).scalars().all()
        assert len(all_findings) == 1
        assert all_findings[0].status == "pending_review"

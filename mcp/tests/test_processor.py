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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


@pytest.fixture
async def project_and_artifact(db):
    async with db() as session:
        project = Project(name="Java App", github_url="https://github.com/test/java")
        session.add(project)
        await session.commit()
        await session.refresh(project)

        artifact = Artifact(
            github_artifact_id="999",
            project_id=project.id,
            status="pending",
        )
        session.add(artifact)
        await session.commit()
        await session.refresh(artifact)
        return project.id, artifact.id


def _make_sarif_zip(num_findings: int = 2) -> bytes:
    results = [
        {
            "ruleId": f"python.lang.security.rule-{i}",
            "level": "error",
            "message": {"text": f"Security issue {i}"},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": f"src/module_{i}.py"},
                    "region": {"startLine": i * 10}
                }
            }]
        }
        for i in range(num_findings)
    ]
    sarif_content = json.dumps({
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "Semgrep"}}, "results": results}]
    })
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("results.sarif", sarif_content)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_artifact_stores_findings(db, project_and_artifact):
    _, artifact_id = project_and_artifact

    mock_github = AsyncMock()
    mock_github.fetch_artifact.return_value = [
        {"filename": "results.sarif", "content": json.dumps({
            "version": "2.1.0",
            "runs": [{"tool": {"driver": {"name": "Semgrep"}}, "results": [
                {
                    "ruleId": "python.lang.security.exec-use",
                    "level": "error",
                    "message": {"text": "Use of exec()"},
                    "locations": [{"physicalLocation": {
                        "artifactLocation": {"uri": "src/app.py"},
                        "region": {"startLine": 42}
                    }}]
                }
            ]}]
        })}
    ]

    processor = SecurityProcessor(session_factory=db, github_client=mock_github)
    count = await processor.process_artifact(artifact_id, github_artifact_id=999)

    assert count == 1
    async with db() as session:
        result = await session.execute(
            select(Finding).where(Finding.artifact_id == artifact_id)
        )
        findings = result.scalars().all()
    assert len(findings) == 1
    assert findings[0].tool == "semgrep"
    assert findings[0].severity == "high"


@pytest.mark.asyncio
async def test_process_artifact_marks_status_processed(db, project_and_artifact):
    _, artifact_id = project_and_artifact

    mock_github = AsyncMock()
    mock_github.fetch_artifact.return_value = []  # no files → 0 findings

    processor = SecurityProcessor(session_factory=db, github_client=mock_github)
    await processor.process_artifact(artifact_id, github_artifact_id=999)

    async with db() as session:
        artifact = await session.get(Artifact, artifact_id)
    assert artifact.status == "processed"


@pytest.mark.asyncio
async def test_process_artifact_marks_status_failed_on_error(db, project_and_artifact):
    _, artifact_id = project_and_artifact

    mock_github = AsyncMock()
    mock_github.fetch_artifact.side_effect = RuntimeError("GitHub unreachable")

    processor = SecurityProcessor(session_factory=db, github_client=mock_github)
    with pytest.raises(RuntimeError):
        await processor.process_artifact(artifact_id, github_artifact_id=999)

    async with db() as session:
        artifact = await session.get(Artifact, artifact_id)
    assert artifact.status == "failed"


@pytest.mark.asyncio
async def test_process_artifact_raises_if_not_found(db):
    mock_github = AsyncMock()
    processor = SecurityProcessor(session_factory=db, github_client=mock_github)

    with pytest.raises(ValueError, match="not found"):
        await processor.process_artifact(db_artifact_id=9999, github_artifact_id=1)


# ---------------------------------------------------------------------------
# V2.8 B2 — per-project GitHub client routing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_run_uses_per_project_client_when_credentials_set(db, monkeypatch):
    """Project có github_token+owner+repo → SecurityProcessor build
    per-project GitHubClient (KHÔNG dùng env)."""
    # Seed project có credentials
    async with db() as session:
        proj = Project(
            name="ALOUTE",
            github_url="https://github.com/cochecheee/SAST_CICD",
            github_owner="cochecheee",
            github_repo="SAST_CICD",
            github_token="ghp_aloute_token",
        )
        session.add(proj)
        await session.commit()
        await session.refresh(proj)
        pid = proj.id

    # Capture which client class is instantiated
    instances: list = []

    from src.services import github_client as gh_mod
    original_for_project = gh_mod.GitHubClient.for_project

    @classmethod
    def spy_for_project(cls, project):
        client = original_for_project(project)
        instances.append(("for_project", project.github_owner, project.github_repo))
        # Stub remote calls
        client.list_artifacts = AsyncMock(return_value=[])
        return client

    monkeypatch.setattr(gh_mod.GitHubClient, "for_project", spy_for_project)

    env_client = AsyncMock()
    env_client.list_artifacts = AsyncMock(return_value=[])
    processor = SecurityProcessor(session_factory=db, github_client=env_client)

    await processor.process_run(project_id=pid, github_run_id=12345)

    # Per-project path called
    assert len(instances) == 1
    assert instances[0] == ("for_project", "cochecheee", "SAST_CICD")
    # Env client NOT used
    env_client.list_artifacts.assert_not_called()


@pytest.mark.asyncio
async def test_process_run_falls_back_to_env_when_no_credentials(db):
    """Project credentials trống → fallback env-bound github_client."""
    async with db() as session:
        proj = Project(
            name="legacy",
            github_url="https://github.com/x/y",
            # github_token/owner/repo intentionally empty
        )
        session.add(proj)
        await session.commit()
        await session.refresh(proj)
        pid = proj.id

    env_client = AsyncMock()
    env_client.list_artifacts = AsyncMock(return_value=[])
    processor = SecurityProcessor(session_factory=db, github_client=env_client)
    await processor.process_run(project_id=pid, github_run_id=99)

    env_client.list_artifacts.assert_awaited_once_with(99)


@pytest.mark.asyncio
async def test_process_run_handles_missing_project_falls_back(db):
    """project_id không tồn tại → fallback env (không raise)."""
    env_client = AsyncMock()
    env_client.list_artifacts = AsyncMock(return_value=[])
    processor = SecurityProcessor(session_factory=db, github_client=env_client)
    await processor.process_run(project_id=99999, github_run_id=77)
    env_client.list_artifacts.assert_awaited_once_with(77)


@pytest.mark.asyncio
async def test_process_artifact_deduplicates_within_batch(db, project_and_artifact):
    _, artifact_id = project_and_artifact

    duplicate_result = {
        "ruleId": "rule-same",
        "level": "warning",
        "message": {"text": "Duplicate finding"},
        "locations": [{"physicalLocation": {
            "artifactLocation": {"uri": "src/dup.py"},
            "region": {"startLine": 1}
        }}]
    }
    sarif = json.dumps({
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "Semgrep"}},
                  "results": [duplicate_result, duplicate_result]}]
    })
    mock_github = AsyncMock()
    mock_github.fetch_artifact.return_value = [
        {"filename": "results.sarif", "content": sarif}
    ]

    processor = SecurityProcessor(session_factory=db, github_client=mock_github)
    count = await processor.process_artifact(artifact_id, github_artifact_id=999)

    assert count == 1  # deduplicated from 2 → 1

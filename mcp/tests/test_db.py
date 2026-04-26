import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.db import Base
from src.models.entities import Artifact, ArtifactStatus, Finding, Project


@pytest.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_project(db_session):
    project = Project(name="Test Project", github_url="https://github.com/test/repo")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    assert project.id is not None
    assert project.name == "Test Project"


@pytest.mark.asyncio
async def test_create_artifact(db_session):
    project = Project(name="Test Project 2", github_url="https://github.com/test/repo2")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    artifact = Artifact(
        github_artifact_id="artifact-123",
        project_id=project.id,
        status=ArtifactStatus.pending.value,
    )
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)
    assert artifact.id is not None
    assert artifact.status == "pending"


@pytest.mark.asyncio
async def test_create_finding(db_session):
    project = Project(name="Test Project 3", github_url="https://github.com/test/repo3")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    artifact = Artifact(github_artifact_id="artifact-456", project_id=project.id)
    db_session.add(artifact)
    await db_session.commit()
    await db_session.refresh(artifact)

    finding = Finding(
        artifact_id=artifact.id,
        tool="semgrep",
        rule_id="python.lang.security.audit.exec-use",
        severity="high",
        message="Use of exec() detected",
        file_path="src/app.py",
        line_number=42,
        cwe_id="CWE-78",
    )
    db_session.add(finding)
    await db_session.commit()
    await db_session.refresh(finding)
    assert finding.id is not None
    assert finding.tool == "semgrep"
    assert finding.cwe_id == "CWE-78"

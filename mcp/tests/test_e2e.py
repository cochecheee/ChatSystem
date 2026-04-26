"""End-to-end test: GitHub artifact → scrub → normalize → enrich → DB storage."""
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
async def setup(db):
    async with db() as session:
        project = Project(name="Java App", github_url="https://github.com/org/java-app")
        session.add(project)
        await session.commit()
        await session.refresh(project)

        artifact = Artifact(
            github_artifact_id="42",
            project_id=project.id,
            status="pending",
        )
        session.add(artifact)
        await session.commit()
        await session.refresh(artifact)
        return project.id, artifact.id


def _sarif_zip(findings: list[dict]) -> bytes:
    sarif = json.dumps({
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "Semgrep"}},
            "results": findings,
        }]
    })
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("semgrep.sarif", sarif)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# E2E: full pipeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_sarif_findings_stored_in_db(db, setup):
    project_id, artifact_id = setup

    sarif_findings = [
        {
            "ruleId": "python.lang.security.exec-use",
            "level": "error",
            "message": {"text": "Use of exec() detected"},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": "src/app.py"},
                "region": {"startLine": 42},
            }}],
        },
        {
            "ruleId": "python.lang.security.sql-injection",
            "level": "warning",
            "message": {"text": "SQL injection vulnerability"},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": "src/db.py"},
                "region": {"startLine": 15},
            }}],
        },
    ]

    mock_github = AsyncMock()
    mock_github.fetch_artifact.return_value = [
        {"filename": "semgrep.sarif", "content": json.dumps({
            "version": "2.1.0",
            "runs": [{"tool": {"driver": {"name": "Semgrep"}}, "results": sarif_findings}]
        })}
    ]

    processor = SecurityProcessor(session_factory=db, github_client=mock_github)
    count = await processor.process_artifact(artifact_id, github_artifact_id=42)

    assert count == 2

    async with db() as session:
        result = await session.execute(
            select(Finding).where(Finding.artifact_id == artifact_id)
        )
        findings = result.scalars().all()

    assert len(findings) == 2
    severities = {f.severity for f in findings}
    assert "high" in severities
    assert "medium" in severities


@pytest.mark.asyncio
async def test_e2e_findings_have_cvss_score(db, setup):
    _, artifact_id = setup

    mock_github = AsyncMock()
    mock_github.fetch_artifact.return_value = [
        {"filename": "results.sarif", "content": json.dumps({
            "version": "2.1.0",
            "runs": [{"tool": {"driver": {"name": "CodeQL"}}, "results": [
                {
                    "ruleId": "java/sql-injection",
                    "level": "error",
                    "message": {"text": "SQL injection"},
                    "locations": [{"physicalLocation": {
                        "artifactLocation": {"uri": "src/Dao.java"},
                        "region": {"startLine": 20},
                    }}],
                }
            ]}]
        })}
    ]

    processor = SecurityProcessor(session_factory=db, github_client=mock_github)
    await processor.process_artifact(artifact_id, github_artifact_id=42)

    async with db() as session:
        result = await session.execute(select(Finding).where(Finding.artifact_id == artifact_id))
        finding = result.scalars().first()

    assert finding is not None
    assert finding.cvss_score is not None
    assert finding.cvss_score > 0


@pytest.mark.asyncio
async def test_e2e_scrubbing_applied_to_findings(db, setup):
    _, artifact_id = setup

    mock_github = AsyncMock()
    mock_github.fetch_artifact.return_value = [
        {"filename": "results.sarif", "content": json.dumps({
            "version": "2.1.0",
            "runs": [{"tool": {"driver": {"name": "Semgrep"}}, "results": [
                {
                    "ruleId": "secret-detection",
                    "level": "error",
                    "message": {"text": "Contact admin@company.com for the leaked key"},
                    "locations": [{"physicalLocation": {
                        "artifactLocation": {"uri": "src/config.py"},
                        "region": {"startLine": 1},
                    }}],
                }
            ]}]
        })}
    ]

    processor = SecurityProcessor(session_factory=db, github_client=mock_github)
    await processor.process_artifact(artifact_id, github_artifact_id=42)

    async with db() as session:
        result = await session.execute(select(Finding).where(Finding.artifact_id == artifact_id))
        finding = result.scalars().first()

    assert finding is not None
    assert "admin@company.com" not in finding.message
    assert "[EMAIL_SCRUBBED]" in finding.message


@pytest.mark.asyncio
async def test_e2e_spotbugs_xml_stored(db, setup):
    _, artifact_id = setup

    spotbugs_xml = """<?xml version="1.0" encoding="UTF-8"?>
<BugCollection version="4.8.6">
  <BugInstance type="SQL_INJECTION_JDBC" priority="1" rank="1" category="SECURITY" cweid="89">
    <ShortMessage>SQL injection via JDBC</ShortMessage>
    <SourceLine classname="com.example.Dao" start="55" sourcepath="Dao.java"/>
  </BugInstance>
</BugCollection>"""

    mock_github = AsyncMock()
    mock_github.fetch_artifact.return_value = [
        {"filename": "spotbugs.xml", "content": spotbugs_xml}
    ]

    processor = SecurityProcessor(session_factory=db, github_client=mock_github)
    count = await processor.process_artifact(artifact_id, github_artifact_id=42)

    assert count == 1

    async with db() as session:
        result = await session.execute(select(Finding).where(Finding.artifact_id == artifact_id))
        finding = result.scalars().first()

    assert finding.tool == "spotbugs"
    assert finding.cwe_id == "CWE-89"
    assert finding.cvss_score is not None  # enriched from CWE-89 → high → 7.5
    assert "A03" in finding.raw_data.get("owasp_category", "")

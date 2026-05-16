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


# ---------------------------------------------------------------------------
# V3.1 Tier 4 — gate-count endpoint + exclude_revoked filter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gate_count_excludes_revoked(client, db_session):
    """The Security Gate composite reads /findings/gate-count for verdict.
    REVOKED findings must NOT count toward critical/high totals.
    """
    p = Project(name="P", github_url="https://github.com/test/x")
    db_session.add(p)
    await db_session.flush()
    a = Artifact(github_artifact_id="x", project_id=p.id, github_run_id=42, status="processed")
    db_session.add(a)
    await db_session.flush()
    db_session.add_all([
        Finding(artifact_id=a.id, tool="semgrep", rule_id="r1", severity="critical",
                message="m", file_path="f.py", status="pending_review"),
        Finding(artifact_id=a.id, tool="codeql", rule_id="r2", severity="high",
                message="m", file_path="f.py", status="REVOKED"),
        Finding(artifact_id=a.id, tool="codeql", rule_id="r3", severity="high",
                message="m", file_path="f.py", status="pending_review"),
    ])
    await db_session.commit()

    resp = await client.get(f"/findings/gate-count?project_id={p.id}&run_id=42")
    assert resp.status_code == 200
    body = resp.json()
    assert body["critical"] == 1   # 1 pending
    assert body["high"] == 1        # 1 pending, 1 revoked excluded
    assert body["exclude_revoked"] is True


@pytest.mark.asyncio
async def test_findings_exclude_revoked_param(client, db_session):
    """GET /findings?exclude_revoked=true filters out REVOKED rows."""
    p = Project(name="P", github_url="https://github.com/test/y")
    db_session.add(p)
    await db_session.flush()
    a = Artifact(github_artifact_id="y", project_id=p.id, github_run_id=7, status="processed")
    db_session.add(a)
    await db_session.flush()
    db_session.add_all([
        Finding(artifact_id=a.id, tool="trivy", rule_id="cve1", severity="high",
                message="m", file_path="g.py", status="pending_review"),
        Finding(artifact_id=a.id, tool="trivy", rule_id="cve2", severity="high",
                message="m", file_path="g.py", status="REVOKED"),
    ])
    await db_session.commit()

    all_findings = (await client.get(f"/findings?project_id={p.id}")).json()
    active = (await client.get(f"/findings?project_id={p.id}&exclude_revoked=true")).json()
    assert len(all_findings) == 2
    assert len(active) == 1
    assert active[0]["status"] != "REVOKED"


@pytest.mark.asyncio
async def test_findings_run_id_filter(client, db_session):
    """GET /findings?run_id= filters to that workflow run's artifacts only."""
    p = Project(name="P", github_url="https://github.com/test/z")
    db_session.add(p)
    await db_session.flush()
    a1 = Artifact(github_artifact_id="z1", project_id=p.id, github_run_id=100, status="processed")
    a2 = Artifact(github_artifact_id="z2", project_id=p.id, github_run_id=200, status="processed")
    db_session.add_all([a1, a2])
    await db_session.flush()
    db_session.add_all([
        Finding(artifact_id=a1.id, tool="trivy", rule_id="r1", severity="high",
                message="m", file_path="f.py", status="pending_review"),
        Finding(artifact_id=a2.id, tool="trivy", rule_id="r2", severity="high",
                message="m", file_path="f.py", status="pending_review"),
    ])
    await db_session.commit()

    run100 = (await client.get(f"/findings?run_id=100")).json()
    run200 = (await client.get(f"/findings?run_id=200")).json()
    assert len(run100) == 1 and run100[0]["rule_id"] == "r1"
    assert len(run200) == 1 and run200[0]["rule_id"] == "r2"


# ---------------------------------------------------------------------------
# V3.1 Tier 2 — suppression rules
# ---------------------------------------------------------------------------

async def _login_admin(client) -> str:
    resp = await client.post(
        "/api/chat/auth/token",
        json={"username": "root", "role": "admin"},
    )
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_suppression_crud_admin(client, project):
    """Admin can create/list/delete suppression rules."""
    admin = await _login_admin(client)
    headers = {"Authorization": f"Bearer {admin}"}

    resp = await client.post(
        f"/projects/{project['id']}/suppressions",
        json={
            "rule_id": "java/path-injection",
            "file_glob": "src/test/**",
            "reason": "Test code, not production path",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    rule_id = resp.json()["id"]

    listed = (await client.get(f"/projects/{project['id']}/suppressions")).json()
    assert any(r["id"] == rule_id for r in listed)

    resp = await client.delete(
        f"/projects/{project['id']}/suppressions/{rule_id}", headers=headers,
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_suppression_requires_security_lead(client, project):
    """A plain developer without project membership cannot create rules."""
    resp = await client.post(
        "/api/chat/auth/token",
        json={"username": "junior", "role": "developer"},
    )
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        f"/projects/{project['id']}/suppressions",
        json={"reason": "Why not"},
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_suppression_rule_matches_at_ingest(db):
    """A matching rule auto-revokes new findings on ingest."""
    from src.models.entities import SuppressionRule
    project_id, artifact_id = await _create_project_and_artifact(db, "art-rule")
    async with db() as session:
        session.add(SuppressionRule(
            project_id=project_id,
            rule_id="python.lang.security.exec-use",
            file_glob="src/*.py",
            tool="semgrep",
            severity_max="critical",
            reason="Internal-use only — exec() is intentional",
            created_by="alice",
        ))
        await session.commit()

    await _ingest(db, artifact_id)

    async with db() as session:
        f = (await session.execute(select(Finding))).scalar_one()
        assert f.status == "REVOKED"
        assert f.revoked_by.startswith("auto-suppress (rule #")
        assert "Internal-use only" in f.revoke_justification


@pytest.mark.asyncio
async def test_suppression_rule_glob_mismatch(db):
    """Rule with file_glob that doesn't match leaves the finding pending."""
    from src.models.entities import SuppressionRule
    project_id, artifact_id = await _create_project_and_artifact(db, "art-no-glob")
    async with db() as session:
        session.add(SuppressionRule(
            project_id=project_id,
            rule_id="python.lang.security.exec-use",
            file_glob="src/test/**",   # Sample SARIF puts file at src/app.py — won't match
            reason="Only test code is exempt",
            created_by="alice",
        ))
        await session.commit()

    await _ingest(db, artifact_id)

    async with db() as session:
        f = (await session.execute(select(Finding))).scalar_one()
        assert f.status == "pending_review"


@pytest.mark.asyncio
async def test_expired_suppression_inactive(db):
    """A rule past its expires_at must not match."""
    from datetime import datetime, UTC, timedelta
    from src.models.entities import SuppressionRule
    project_id, artifact_id = await _create_project_and_artifact(db, "art-expired")
    async with db() as session:
        session.add(SuppressionRule(
            project_id=project_id,
            rule_id="python.lang.security.exec-use",
            reason="Expired rule",
            created_by="alice",
            expires_at=datetime.now(UTC) - timedelta(days=1),
        ))
        await session.commit()

    await _ingest(db, artifact_id)

    async with db() as session:
        f = (await session.execute(select(Finding))).scalar_one()
        assert f.status == "pending_review"


# ---------------------------------------------------------------------------
# V3.1 Tier 3 — AI batch triage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_triage_service_auto_revokes_high_confidence_fp(db):
    """Stubbed LLM classifies one of two findings as FALSE_POSITIVE @ 0.95 →
    only that one is auto-revoked; the other (TRUE_POSITIVE) stays pending."""
    from src.services.llm.triage import TriageService, TriageBatch, TriageItem

    project_id, artifact_id = await _create_project_and_artifact(db, "art-triage")

    async with db() as session:
        f1 = Finding(
            artifact_id=artifact_id, tool="semgrep", rule_id="r1",
            severity="high", message="exec()", file_path="src/a.py",
            status="pending_review", dedup_hash="h1",
        )
        f2 = Finding(
            artifact_id=artifact_id, tool="semgrep", rule_id="r2",
            severity="critical", message="path traversal", file_path="src/b.py",
            status="pending_review", dedup_hash="h2",
        )
        session.add_all([f1, f2])
        await session.commit()
        await session.refresh(f1)
        await session.refresh(f2)
        f1_id, f2_id = f1.id, f2.id

    async def stub_llm(client, findings):
        return TriageBatch(items=[
            TriageItem(finding_id=f1_id, classification="FALSE_POSITIVE",
                       confidence=0.95, reason="Intended in test fixture"),
            TriageItem(finding_id=f2_id, classification="TRUE_POSITIVE",
                       confidence=0.90, reason="Real RCE risk"),
        ])

    svc = TriageService(llm_caller=stub_llm)
    async with db() as session:
        findings = (await session.execute(
            select(Finding).where(Finding.id.in_([f1_id, f2_id]))
        )).scalars().all()
        result = await svc.triage_findings(session, list(findings))

    assert result["classifications"]["FALSE_POSITIVE"] == 1
    assert result["classifications"]["TRUE_POSITIVE"] == 1
    assert result["auto_revoked"] == 1

    async with db() as session:
        fresh = (await session.execute(
            select(Finding).order_by(Finding.id)
        )).scalars().all()
        statuses = {f.id: f.status for f in fresh}
        assert statuses[f1_id] == "REVOKED"
        assert statuses[f2_id] == "pending_review"


@pytest.mark.asyncio
async def test_triage_dry_run_does_not_revoke(db):
    """dry_run=true: classify but don't write."""
    from src.services.llm.triage import TriageService, TriageBatch, TriageItem

    project_id, artifact_id = await _create_project_and_artifact(db, "art-dry")
    async with db() as session:
        f = Finding(
            artifact_id=artifact_id, tool="semgrep", rule_id="r",
            severity="high", message="m", file_path="x.py",
            status="pending_review", dedup_hash="hd",
        )
        session.add(f)
        await session.commit()
        await session.refresh(f)
        fid = f.id

    async def stub_llm(client, findings):
        return TriageBatch(items=[TriageItem(
            finding_id=fid, classification="FALSE_POSITIVE",
            confidence=0.99, reason="x",
        )])

    svc = TriageService(llm_caller=stub_llm)
    async with db() as session:
        findings = list((await session.execute(select(Finding))).scalars().all())
        result = await svc.triage_findings(session, findings, dry_run=True)

    assert result["auto_revoked"] == 0
    assert result["items"][0]["applied"] is False
    async with db() as session:
        unchanged = (await session.execute(select(Finding))).scalar_one()
        assert unchanged.status == "pending_review"


@pytest.mark.asyncio
async def test_triage_low_confidence_left_alone(db):
    """Confidence below threshold → no auto-revoke even when FALSE_POSITIVE."""
    from src.services.llm.triage import TriageService, TriageBatch, TriageItem

    project_id, artifact_id = await _create_project_and_artifact(db, "art-low")
    async with db() as session:
        f = Finding(
            artifact_id=artifact_id, tool="semgrep", rule_id="r",
            severity="high", message="m", file_path="x.py",
            status="pending_review", dedup_hash="hl",
        )
        session.add(f)
        await session.commit()
        await session.refresh(f)
        fid = f.id

    async def stub_llm(client, findings):
        return TriageBatch(items=[TriageItem(
            finding_id=fid, classification="FALSE_POSITIVE",
            confidence=0.50, reason="unsure",
        )])

    svc = TriageService(llm_caller=stub_llm)
    async with db() as session:
        findings = list((await session.execute(select(Finding))).scalars().all())
        result = await svc.triage_findings(
            session, findings, confidence_threshold=0.8,
        )
    assert result["auto_revoked"] == 0


@pytest.mark.asyncio
async def test_triage_batches_at_size(db):
    """When findings > BATCH_SIZE, llm_caller is invoked N=ceil(total/batch) times."""
    from src.services.llm.triage import TriageService, TriageBatch

    project_id, artifact_id = await _create_project_and_artifact(db, "art-batch")
    async with db() as session:
        # 25 findings → 2 batches at BATCH_SIZE=20
        for i in range(25):
            session.add(Finding(
                artifact_id=artifact_id, tool="t", rule_id=f"r-{i}",
                severity="low", message=f"m{i}", file_path=f"f{i}.py",
                status="pending_review", dedup_hash=f"h{i}",
            ))
        await session.commit()

    call_count = 0
    async def stub_llm(client, findings):
        nonlocal call_count
        call_count += 1
        return TriageBatch(items=[])

    svc = TriageService(llm_caller=stub_llm)
    async with db() as session:
        findings = list((await session.execute(select(Finding))).scalars().all())
        result = await svc.triage_findings(session, findings)

    assert call_count == 2  # 25 / 20 → 2 batches
    assert result["batches"] == 2


@pytest.mark.asyncio
async def test_suppression_severity_max_caps(db):
    """severity_max=medium means high/critical findings are NOT auto-revoked."""
    from src.models.entities import SuppressionRule
    project_id, artifact_id = await _create_project_and_artifact(db, "art-sevmax")
    async with db() as session:
        session.add(SuppressionRule(
            project_id=project_id,
            rule_id="python.lang.security.exec-use",
            severity_max="medium",  # SARIF level=error → "high" — above cap
            reason="Only mute medium-and-below for this rule",
            created_by="alice",
        ))
        await session.commit()

    await _ingest(db, artifact_id)
    async with db() as session:
        f = (await session.execute(select(Finding))).scalar_one()
        assert f.status == "pending_review"   # severity=high > severity_max=medium

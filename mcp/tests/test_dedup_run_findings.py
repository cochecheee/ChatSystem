"""V3.9 — within-run dedup: a run publishes both a merged artifact and per-tool
artifacts, so process_run stores each finding once per artifact (raw ~= 2x
unique). `_dedup_run_findings` collapses same-dedup_hash rows within the kept
run to one, preserving triage state and re-pointing audit children, so every
surface (gate-count, KPIs, lists, AI summary) counts the same numbers."""
from sqlalchemy import func, select

from src.core.db import AsyncSessionLocal
from src.models.entities import Artifact, Finding, FindingAction, Project
from src.services.processor import SecurityProcessor


def _finding(
    artifact_id: int, dhash: str, status: str = "pending_review",
    rule: str = "r",
) -> Finding:
    return Finding(
        artifact_id=artifact_id, tool="semgrep", rule_id=rule,
        severity="high", message="m", file_path="f.py",
        dedup_hash=dhash, status=status,
    )


async def _seed_run(run: int = 300, project_name: str = "P"):
    """One run, two artifacts (merged + per-tool) → returns (pid, a1_id, a2_id)."""
    async with AsyncSessionLocal() as s:
        p = Project(name=project_name, github_url="https://github.com/x/y")
        s.add(p)
        await s.commit()
        await s.refresh(p)
        a1 = Artifact(github_artifact_id="1", project_id=p.id, github_run_id=run, status="processed")
        a2 = Artifact(github_artifact_id="2", project_id=p.id, github_run_id=run, status="processed")
        s.add_all([a1, a2])
        await s.commit()
        await s.refresh(a1)
        await s.refresh(a2)
        return p.id, a1.id, a2.id


async def _count(pid: int) -> int:
    async with AsyncSessionLocal() as s:
        return (await s.execute(
            select(func.count(Finding.id))
            .join(Artifact, Finding.artifact_id == Artifact.id)
            .where(Artifact.project_id == pid)
        )).scalar_one()


async def test_dedup_collapses_within_run_duplicates(client):
    pid, a1, a2 = await _seed_run()
    async with AsyncSessionLocal() as s:
        # merged (a1) + per-tool (a2) each carry the SAME 3 findings.
        s.add_all([
            _finding(a1, "h1"), _finding(a1, "h2"), _finding(a1, "h3"),
            _finding(a2, "h1"), _finding(a2, "h2"), _finding(a2, "h3"),
        ])
        await s.commit()
    assert await _count(pid) == 6  # the double-count bug state

    deleted = await SecurityProcessor()._dedup_run_findings(pid, 300)
    assert deleted == 3
    assert await _count(pid) == 3  # one row per dedup_hash


async def test_dedup_is_idempotent(client):
    pid, a1, a2 = await _seed_run()
    async with AsyncSessionLocal() as s:
        s.add_all([_finding(a1, "h1"), _finding(a2, "h1")])
        await s.commit()
    assert await SecurityProcessor()._dedup_run_findings(pid, 300) == 1
    # second pass: nothing left to collapse.
    assert await SecurityProcessor()._dedup_run_findings(pid, 300) == 0
    assert await _count(pid) == 1


async def test_dedup_keeps_decided_status(client):
    pid, a1, a2 = await _seed_run()
    async with AsyncSessionLocal() as s:
        # keeper-by-id would be the pending copy (a1, lower id), but the REVOKED
        # copy (a2) must win so audited triage is never lost.
        s.add_all([
            _finding(a1, "h1", status="pending_review"),
            _finding(a2, "h1", status="REVOKED"),
        ])
        await s.commit()
    deleted = await SecurityProcessor()._dedup_run_findings(pid, 300)
    assert deleted == 1
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(
            select(Finding.status)
            .join(Artifact, Finding.artifact_id == Artifact.id)
            .where(Artifact.project_id == pid)
        )).scalars().all()
    assert rows == ["REVOKED"]  # the decided copy survived


async def test_dedup_repoints_finding_actions(client):
    pid, a1, a2 = await _seed_run()
    async with AsyncSessionLocal() as s:
        keeper = _finding(a1, "h1")           # lower id → keeper
        loser = _finding(a2, "h1")            # higher id → dropped
        s.add_all([keeper, loser])
        await s.commit()
        await s.refresh(keeper)
        await s.refresh(loser)
        keeper_id, loser_id = keeper.id, loser.id
        s.add(FindingAction(
            finding_id=loser_id, action="revoke", submitted_by="dashboard:tester",
        ))
        await s.commit()

    deleted = await SecurityProcessor()._dedup_run_findings(pid, 300)
    assert deleted == 1
    async with AsyncSessionLocal() as s:
        # the action followed the survivor — no dangling FK to a deleted finding.
        action_fids = (await s.execute(select(FindingAction.finding_id))).scalars().all()
        live_fids = (await s.execute(select(Finding.id))).scalars().all()
    assert action_fids == [keeper_id]
    assert loser_id not in live_fids
    assert keeper_id in live_fids


async def test_dedup_guard_skips_older_run(client):
    pid, a1, a2 = await _seed_run(run=100)
    async with AsyncSessionLocal() as s:
        # a newer run exists → dedup on the older run must no-op.
        a_new = Artifact(github_artifact_id="9", project_id=pid, github_run_id=200, status="processed")
        s.add(a_new)
        await s.commit()
        s.add_all([_finding(a1, "h1"), _finding(a2, "h1")])
        await s.commit()
    deleted = await SecurityProcessor()._dedup_run_findings(pid, 100)
    assert deleted == 0
    assert await _count(pid) == 2  # untouched


async def test_dedup_ignores_null_hash(client):
    pid, a1, a2 = await _seed_run()
    async with AsyncSessionLocal() as s:
        # findings without a computable hash cannot be equality-deduped → kept.
        s.add_all([
            _finding(a1, None), _finding(a2, None),
        ])
        await s.commit()
    deleted = await SecurityProcessor()._dedup_run_findings(pid, 300)
    assert deleted == 0
    assert await _count(pid) == 2

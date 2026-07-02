"""V3.8 Option A — current-state storage: process_run prunes findings from
older runs so the DB keeps only the latest scan per project."""
from sqlalchemy import func, select

from src.core.db import AsyncSessionLocal
from src.models.entities import Artifact, Finding, Project
from src.services.processor import SecurityProcessor


def _finding(artifact_id: int, rule: str) -> Finding:
    return Finding(
        artifact_id=artifact_id, tool="semgrep", rule_id=rule,
        severity="high", message="m", file_path="f.py",
    )


async def _seed_two_runs(older: int = 100, newer: int = 200) -> int:
    async with AsyncSessionLocal() as s:
        p = Project(name="P", github_url="https://github.com/x/y")
        s.add(p)
        await s.commit()
        await s.refresh(p)
        a_old = Artifact(github_artifact_id="1", project_id=p.id, github_run_id=older, status="processed")
        a_new = Artifact(github_artifact_id="2", project_id=p.id, github_run_id=newer, status="processed")
        s.add_all([a_old, a_new])
        await s.commit()
        await s.refresh(a_old)
        await s.refresh(a_new)
        s.add_all([
            _finding(a_old.id, "r1"), _finding(a_old.id, "r2"),  # old run: 2
            _finding(a_new.id, "r1"), _finding(a_new.id, "r3"),  # new run: 2
        ])
        await s.commit()
        return p.id


async def _counts_by_run() -> dict[int, int]:
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(
            select(Artifact.github_run_id, func.count(Finding.id))
            .join(Finding, Finding.artifact_id == Artifact.id)
            .group_by(Artifact.github_run_id)
        )).all()
    return {r[0]: r[1] for r in rows}


async def test_prune_keeps_only_latest_run(client):
    pid = await _seed_two_runs()
    deleted = await SecurityProcessor()._prune_superseded_findings(pid, 200)
    assert deleted == 2                       # both older-run findings removed
    assert await _counts_by_run() == {200: 2}  # only newest run remains


async def test_prune_guard_skips_when_reprocessing_old_run(client):
    pid = await _seed_two_runs()
    # keep_run=100 is OLDER than newest (200) → guard must skip, delete nothing.
    deleted = await SecurityProcessor()._prune_superseded_findings(pid, 100)
    assert deleted == 0
    assert await _counts_by_run() == {100: 2, 200: 2}


async def test_prune_noop_single_run(client):
    async with AsyncSessionLocal() as s:
        p = Project(name="Solo", github_url="https://github.com/x/solo")
        s.add(p)
        await s.commit()
        await s.refresh(p)
        a = Artifact(github_artifact_id="1", project_id=p.id, github_run_id=500, status="processed")
        s.add(a)
        await s.commit()
        await s.refresh(a)
        s.add(_finding(a.id, "r1"))
        await s.commit()
        pid = p.id
    deleted = await SecurityProcessor()._prune_superseded_findings(pid, 500)
    assert deleted == 0
    assert await _counts_by_run() == {500: 1}

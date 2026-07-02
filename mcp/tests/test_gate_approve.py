"""§4.2.3 — /approve accepts risk (audited) so APPROVED findings no longer
block the gate. gate-count must exclude BOTH REVOKED and APPROVED."""
from src.core.db import AsyncSessionLocal
from src.models.entities import Artifact, Finding, Project
from src.repositories.finding_repo import FindingRepository


def _f(aid: int, status: str) -> Finding:
    return Finding(
        artifact_id=aid, tool="semgrep", rule_id="r", severity="critical",
        message="m", file_path="f.py", status=status,
    )


async def test_gate_count_excludes_approved_and_revoked(client):
    async with AsyncSessionLocal() as s:
        p = Project(name="P", github_url="https://github.com/x/y")
        s.add(p)
        await s.commit()
        await s.refresh(p)
        a = Artifact(github_artifact_id="1", project_id=p.id, github_run_id=100, status="processed")
        s.add(a)
        await s.commit()
        await s.refresh(a)
        s.add_all([
            _f(a.id, "pending_review"),  # counts
            _f(a.id, "ai_analyzed"),     # counts
            _f(a.id, "APPROVED"),        # excluded (accepted-risk)
            _f(a.id, "REVOKED"),         # excluded (false-positive)
        ])
        await s.commit()
        pid = p.id

    async with AsyncSessionLocal() as s:
        repo = FindingRepository(s)
        gate = await repo.count_with_filters(
            project_id=pid, severity="critical",
            exclude_revoked=True, exclude_approved=True,
        )
        revoked_only = await repo.count_with_filters(
            project_id=pid, severity="critical", exclude_revoked=True,
        )
        raw = await repo.count_with_filters(project_id=pid, severity="critical")

    assert raw == 4              # all criticals
    assert revoked_only == 3     # old behavior: only REVOKED excluded
    assert gate == 2             # new: APPROVED also excluded → 2 active block the gate

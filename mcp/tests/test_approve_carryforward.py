"""§5.2.5/§4.2.3 — an APPROVED finding carries forward by dedup_hash so the gate
does NOT re-flag it on the next run (mirror of REVOKED Tier-1)."""
from sqlalchemy import select
from src.core.db import AsyncSessionLocal
from src.models.entities import Artifact, Finding, Project
from src.repositories.finding_repo import FindingRepository


async def test_find_approved_hashes(client):
    async with AsyncSessionLocal() as s:
        p = Project(name="P", github_url="https://github.com/x/y")
        s.add(p); await s.commit(); await s.refresh(p)
        a = Artifact(github_artifact_id="1", project_id=p.id, github_run_id=1, status="processed")
        s.add(a); await s.commit(); await s.refresh(a)
        s.add_all([
            Finding(artifact_id=a.id, project_id=p.id, tool="t", rule_id="r1", severity="high",
                    message="m", file_path="f.py", status="APPROVED", approved_by="lead",
                    justification="accepted risk internal only", dedup_hash="H-appr"),
            Finding(artifact_id=a.id, project_id=p.id, tool="t", rule_id="r2", severity="high",
                    message="m", file_path="f.py", status="REVOKED", revoked_by="lead",
                    dedup_hash="H-rev"),
            Finding(artifact_id=a.id, project_id=p.id, tool="t", rule_id="r3", severity="high",
                    message="m", file_path="f.py", status="pending_review", dedup_hash="H-open"),
        ])
        await s.commit(); pid = p.id
    async with AsyncSessionLocal() as s:
        appr = await FindingRepository(s).find_approved_hashes({"H-appr", "H-rev", "H-open"}, project_id=pid)
    assert set(appr) == {"H-appr"}                       # only APPROVED carried
    assert appr["H-appr"]["approved_by"] == "lead"
    assert "accepted risk" in appr["H-appr"]["justification"]

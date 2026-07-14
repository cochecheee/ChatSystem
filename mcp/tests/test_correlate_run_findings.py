"""V4.0 — cross-tool correlation: the same vulnerability reported by different
tools (Semgrep/CodeQL/Bandit…) uses different rule_id/message, so the exact-hash
dedup never collapses it. `_correlate_run_findings` clusters the run's surviving
findings by a strict key (category + normalized file + CWE + line window), keeps
one canonical row, records the corroborating tools on the keeper's
raw_data['_correlation'], re-points audit children, and deletes the rest."""
from sqlalchemy import func, select

from src.core.db import AsyncSessionLocal
from src.models.entities import Artifact, Finding, FindingAction, Project
from src.services.processor import SecurityProcessor


def _finding(
    artifact_id: int,
    tool: str,
    *,
    cwe: str | None = "CWE-89",
    line: int | None = 42,
    file: str = "app/users.py",
    severity: str = "high",
    status: str = "pending_review",
    rule: str | None = None,
    raw: dict | None = None,
    owasp: str | None = None,
) -> Finding:
    return Finding(
        artifact_id=artifact_id, tool=tool, rule_id=rule or f"{tool}.rule",
        severity=severity, message=f"{tool} says line {line}", file_path=file,
        line_number=line, cwe_id=cwe, status=status, raw_data=raw,
        owasp_class=owasp,
    )


async def _seed_run(run: int = 300, project_name: str = "P"):
    """One run, one artifact → returns (pid, artifact_id)."""
    async with AsyncSessionLocal() as s:
        p = Project(name=project_name, github_url="https://github.com/x/y")
        s.add(p)
        await s.commit()
        await s.refresh(p)
        a1 = Artifact(
            github_artifact_id="1", project_id=p.id,
            github_run_id=run, status="processed",
        )
        s.add(a1)
        await s.commit()
        await s.refresh(a1)
        return p.id, a1.id


async def _count(pid: int) -> int:
    async with AsyncSessionLocal() as s:
        return (await s.execute(
            select(func.count(Finding.id))
            .join(Artifact, Finding.artifact_id == Artifact.id)
            .where(Artifact.project_id == pid)
        )).scalar_one()


async def _survivor(pid: int) -> Finding:
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(
            select(Finding)
            .join(Artifact, Finding.artifact_id == Artifact.id)
            .where(Artifact.project_id == pid)
        )).scalars().all()
        assert len(rows) == 1
        return rows[0]


async def test_correlate_collapses_cross_tool_cluster(client):
    pid, a1 = await _seed_run()
    async with AsyncSessionLocal() as s:
        # same SAST bug (CWE-89) at ~same line, reported by 3 different tools.
        s.add_all([
            _finding(a1, "semgrep", line=42),
            _finding(a1, "codeql", line=43),
            _finding(a1, "bandit", line=41),
        ])
        await s.commit()
    assert await _count(pid) == 3

    deleted = await SecurityProcessor()._correlate_run_findings(pid, 300)
    assert deleted == 2
    assert await _count(pid) == 1

    keeper = await _survivor(pid)
    corr = (keeper.raw_data or {})["_correlation"]
    assert corr["size"] == 3
    assert set(corr["tools"]) == {"semgrep", "codeql", "bandit"}
    assert len(corr["members"]) == 2  # the two dropped duplicates
    # codeql has the highest tool priority → it becomes the canonical keeper.
    assert keeper.tool == "codeql"
    assert corr["primary_tool"] == "codeql"


async def test_correlate_different_cwe_not_merged(client):
    pid, a1 = await _seed_run()
    async with AsyncSessionLocal() as s:
        s.add_all([
            _finding(a1, "semgrep", cwe="CWE-89"),   # SQLi
            _finding(a1, "codeql", cwe="CWE-79"),     # XSS — different weakness
        ])
        await s.commit()
    assert await SecurityProcessor()._correlate_run_findings(pid, 300) == 0
    assert await _count(pid) == 2


async def test_correlate_missing_cwe_not_merged(client):
    pid, a1 = await _seed_run()
    async with AsyncSessionLocal() as s:
        # no parseable CWE → conservative: never cross-tool-merged.
        s.add_all([
            _finding(a1, "semgrep", cwe=None),
            _finding(a1, "eslint", cwe=None),
        ])
        await s.commit()
    assert await SecurityProcessor()._correlate_run_findings(pid, 300) == 0
    assert await _count(pid) == 2


async def test_correlate_different_category_not_merged(client):
    pid, a1 = await _seed_run()
    async with AsyncSessionLocal() as s:
        # a SAST code finding and a Trivy dependency finding are NOT the same
        # issue even at the same CWE — categories are kept separate.
        s.add_all([
            _finding(a1, "semgrep", cwe="CWE-89"),   # sast
            _finding(a1, "trivy", cwe="CWE-89"),      # deps
        ])
        await s.commit()
    assert await SecurityProcessor()._correlate_run_findings(pid, 300) == 0
    assert await _count(pid) == 2


async def test_correlate_respects_line_window(client):
    pid, a1 = await _seed_run()
    async with AsyncSessionLocal() as s:
        # fileA: lines 42 & 44 fall in the same window (default 5) → merge.
        s.add_all([
            _finding(a1, "semgrep", file="a.py", line=42),
            _finding(a1, "codeql", file="a.py", line=44),
        ])
        # fileB: lines 10 & 90 are far apart → stay separate.
        s.add_all([
            _finding(a1, "semgrep", file="b.py", line=10),
            _finding(a1, "codeql", file="b.py", line=90),
        ])
        await s.commit()
    assert await _count(pid) == 4
    deleted = await SecurityProcessor()._correlate_run_findings(pid, 300)
    assert deleted == 1              # only fileA collapsed
    assert await _count(pid) == 3

    async with AsyncSessionLocal() as s:
        b_rows = (await s.execute(
            select(func.count(Finding.id))
            .join(Artifact, Finding.artifact_id == Artifact.id)
            .where(Artifact.project_id == pid, Finding.file_path == "b.py")
        )).scalar_one()
    assert b_rows == 2               # fileB untouched


async def test_correlate_keeps_decided_status(client):
    pid, a1 = await _seed_run()
    async with AsyncSessionLocal() as s:
        # bandit has LOWER tool priority than codeql, but its REVOKED status
        # must win so audited triage is never lost.
        s.add_all([
            _finding(a1, "bandit", line=42, status="REVOKED"),
            _finding(a1, "codeql", line=43, status="pending_review"),
        ])
        await s.commit()
    deleted = await SecurityProcessor()._correlate_run_findings(pid, 300)
    assert deleted == 1
    keeper = await _survivor(pid)
    assert keeper.status == "REVOKED"
    assert keeper.tool == "bandit"


async def test_correlate_repoints_finding_actions(client):
    pid, a1 = await _seed_run()
    async with AsyncSessionLocal() as s:
        keeper = _finding(a1, "codeql", line=42)     # highest tool priority
        loser = _finding(a1, "semgrep", line=43)
        s.add_all([keeper, loser])
        await s.commit()
        await s.refresh(keeper)
        await s.refresh(loser)
        keeper_id, loser_id = keeper.id, loser.id
        s.add(FindingAction(
            finding_id=loser_id, action="revoke", submitted_by="dashboard:tester",
        ))
        await s.commit()

    deleted = await SecurityProcessor()._correlate_run_findings(pid, 300)
    assert deleted == 1
    async with AsyncSessionLocal() as s:
        action_fids = (await s.execute(select(FindingAction.finding_id))).scalars().all()
        live_fids = (await s.execute(select(Finding.id))).scalars().all()
    assert action_fids == [keeper_id]       # action followed the survivor
    assert loser_id not in live_fids
    assert keeper_id in live_fids


async def test_correlate_is_idempotent(client):
    pid, a1 = await _seed_run()
    async with AsyncSessionLocal() as s:
        s.add_all([
            _finding(a1, "semgrep", line=42),
            _finding(a1, "codeql", line=43),
        ])
        await s.commit()
    assert await SecurityProcessor()._correlate_run_findings(pid, 300) == 1
    # second pass: the cluster is already a single row → nothing to collapse.
    assert await SecurityProcessor()._correlate_run_findings(pid, 300) == 0
    assert await _count(pid) == 1


async def test_dedup_stats_endpoint(client):
    pid, a1 = await _seed_run()
    async with AsyncSessionLocal() as s:
        s.add_all([
            _finding(a1, "semgrep", line=42),
            _finding(a1, "codeql", line=43),
            _finding(a1, "bandit", line=41),
        ])
        await s.commit()
    await SecurityProcessor()._correlate_run_findings(pid, 300)

    r = await client.get(
        "/findings/dedup-stats", params={"project_id": pid, "run_id": 300},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["unique_findings"] == 1
    assert data["raw_findings_estimate"] == 3
    assert data["cross_tool_duplicates_removed"] == 2
    assert data["multi_tool_clusters"] == 1
    assert data["reduction_pct"] == round(100 * 2 / 3, 1)
    assert len(data["clusters"]) == 1
    assert set(data["clusters"][0]["tools"]) == {"semgrep", "codeql", "bandit"}
    assert data["clusters"][0]["primary_tool"] == "codeql"


async def test_category_stats_endpoint(client):
    """V4.4 — OWASP class distribution + uncategorized count."""
    pid, a1 = await _seed_run()
    async with AsyncSessionLocal() as s:
        s.add_all([
            _finding(a1, "semgrep", file="a.py", owasp="A03"),
            _finding(a1, "codeql", file="b.py", owasp="A03"),
            _finding(a1, "bandit", file="c.py", owasp="A01"),
            _finding(a1, "eslint", file="d.py", owasp=None),   # uncategorized
        ])
        await s.commit()

    r = await client.get(
        "/findings/category-stats", params={"project_id": pid, "run_id": 300},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 4
    assert data["with_class"] == 3
    assert data["uncategorized"] == 1
    assert data["by_class"]["A03"] == 2
    assert data["by_class"]["A01"] == 1
    assert data["by_class"]["A00"] == 1


async def test_owasp_class_filter(client):
    """V4.4 — /findings?owasp_class=A03 returns only that class."""
    pid, a1 = await _seed_run()
    async with AsyncSessionLocal() as s:
        s.add_all([
            _finding(a1, "semgrep", file="a.py", owasp="A03"),
            _finding(a1, "codeql", file="b.py", owasp="A03"),
            _finding(a1, "bandit", file="c.py", owasp="A01"),
        ])
        await s.commit()

    r = await client.get(
        "/findings", params={"project_id": pid, "run_id": 300, "owasp_class": "A03"},
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    assert all(f["owasp_class"] == "A03" for f in rows)
    assert r.headers["X-Total-Count"] == "2"


async def test_correlate_guard_skips_older_run(client):
    pid, a1 = await _seed_run(run=100)
    async with AsyncSessionLocal() as s:
        # a newer run exists → correlation on the older run must no-op.
        a_new = Artifact(
            github_artifact_id="9", project_id=pid,
            github_run_id=200, status="processed",
        )
        s.add(a_new)
        await s.commit()
        s.add_all([
            _finding(a1, "semgrep", line=42),
            _finding(a1, "codeql", line=43),
        ])
        await s.commit()
    assert await SecurityProcessor()._correlate_run_findings(pid, 100) == 0
    assert await _count(pid) == 2       # untouched

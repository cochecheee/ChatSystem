"""V3.3 Part B — AI summary endpoint tests.

LLM call is stubbed so tests are deterministic and don't burn quota. The
caching, fallback (empty project), and force_refresh paths are covered.
"""
from unittest.mock import AsyncMock, patch

import pytest

from src.models.entities import Artifact, Finding, Project
from src.services.llm.summary import (
    AiSummaryOutput,
    SummaryService,
    TopRisk,
    _pick_diverse,
    _risk_group_key,
    clear_cache,
)


# V3.4 — stub the GitHub call in the pipeline_health path. Without this
# patch _gather_stats would try to hit api.github.com.
@pytest.fixture(autouse=True)
def _stub_github_runs():
    with patch("src.services.github_client.GitHubClient.list_workflow_runs",
               new=AsyncMock(return_value=[])):
        yield


@pytest.fixture(autouse=True)
def _reset_summary_cache():
    """Each test starts with a clean in-memory cache."""
    clear_cache()
    yield
    clear_cache()


async def _seed_findings(db_session, project: Project, n_critical: int, n_high: int) -> None:
    art = Artifact(github_artifact_id="s", project_id=project.id, github_run_id=1, status="processed")
    db_session.add(art)
    await db_session.flush()
    for i in range(n_critical):
        db_session.add(Finding(
            artifact_id=art.id, tool="codeql", rule_id=f"java/crit-{i}",
            severity="critical", message=f"Crit {i}", file_path=f"a{i}.java",
            status="pending_review", dedup_hash=f"c{i}",
        ))
    for i in range(n_high):
        db_session.add(Finding(
            artifact_id=art.id, tool="trivy", rule_id=f"CVE-{i}",
            severity="high", message=f"CVE high {i}", file_path=f"b{i}.java",
            status="pending_review", dedup_hash=f"h{i}",
        ))
    await db_session.commit()


def _stub_llm_factory(overview="Test overview", recs="1. Fix it"):
    """Returns an awaitable that ignores its inputs and returns a fixed output."""
    async def stub(client, prompt):
        return AiSummaryOutput(
            overview_md=overview,
            top_risks=[
                TopRisk(
                    severity="critical", rule_id="java/path-injection",
                    file_path="src/Foo.java",
                    one_line_reason="Path injection cho phép RCE qua user input",
                    finding_id=1,
                ),
            ],
            recommendations_md=recs,
        )
    return stub


@pytest.mark.asyncio
async def test_summary_empty_project_skips_llm(client, db_session):
    """Empty project — service should NOT call Gemini, return clean message."""
    p = Project(name="Empty", github_url="https://github.com/test/empty")
    db_session.add(p)
    await db_session.commit()

    call_count = 0
    async def counting_stub(client, prompt):
        nonlocal call_count
        call_count += 1
        return AiSummaryOutput(overview_md="x", top_risks=[], recommendations_md="x")

    svc = SummaryService(llm_caller=counting_stub)
    result = await svc.generate(db_session, project_id=p.id, run_id=None)
    assert call_count == 0
    assert "sạch" in result.overview_md


@pytest.mark.asyncio
async def test_summary_returns_structured_output(client, db_session):
    p = Project(name="P", github_url="https://github.com/test/p-summary")
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    await _seed_findings(db_session, p, n_critical=2, n_high=3)

    svc = SummaryService(llm_caller=_stub_llm_factory())
    # autouse fixture returns [] from GitHub → runs_total=0 (truthful: we
    # have local artifacts but no GitHub conclusion data). The structured
    # output fields are what matters here.
    r = await svc.generate(db_session, project_id=p.id, run_id=None)
    assert r.overview_md == "Test overview"
    assert r.recommendations_md == "1. Fix it"
    assert len(r.top_risks) == 1
    assert r.top_risks[0].severity == "critical"
    assert r.pipeline_health is not None


@pytest.mark.asyncio
async def test_summary_cached_on_second_call(client, db_session):
    p = Project(name="P", github_url="https://github.com/test/p-cached")
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    await _seed_findings(db_session, p, n_critical=1, n_high=1)

    call_count = 0
    async def counting_stub(client, prompt):
        nonlocal call_count
        call_count += 1
        return AiSummaryOutput(
            overview_md="One", top_risks=[], recommendations_md="One",
        )

    svc = SummaryService(llm_caller=counting_stub)
    r1 = await svc.generate(db_session, project_id=p.id, run_id=None)
    r2 = await svc.generate(db_session, project_id=p.id, run_id=None)
    assert call_count == 1, "Second call should hit cache"
    assert r1.cached is False
    assert r2.cached is True
    assert r2.cache_ttl_remaining <= r1.cache_ttl_remaining + 1


@pytest.mark.asyncio
async def test_summary_force_refresh_bypasses_cache(client, db_session):
    p = Project(name="P", github_url="https://github.com/test/p-refresh")
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    await _seed_findings(db_session, p, n_critical=1, n_high=0)

    call_count = 0
    async def counting_stub(client, prompt):
        nonlocal call_count
        call_count += 1
        return AiSummaryOutput(
            overview_md=f"call {call_count}", top_risks=[], recommendations_md="x",
        )

    svc = SummaryService(llm_caller=counting_stub)
    await svc.generate(db_session, project_id=p.id, run_id=None)
    r2 = await svc.generate(db_session, project_id=p.id, run_id=None, force_refresh=True)
    assert call_count == 2
    assert r2.cached is False
    assert r2.overview_md == "call 2"


# ---------------------------------------------------------------------------
# V3.4 — accuracy fixes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_active_counts_exclude_revoked(client, db_session):
    """V3.4 BUG-2 — primary numbers passed to Gemini must be ACTIVE counts."""
    p = Project(name="P", github_url="https://github.com/test/active")
    db_session.add(p)
    await db_session.flush()
    a = Artifact(github_artifact_id="x", project_id=p.id, github_run_id=1, status="processed")
    db_session.add(a)
    await db_session.flush()
    db_session.add_all([
        Finding(artifact_id=a.id, tool="t", rule_id="r1", severity="critical",
                message="m", file_path="x.py", status="pending_review", dedup_hash="a"),
        Finding(artifact_id=a.id, tool="t", rule_id="r2", severity="critical",
                message="m", file_path="x.py", status="REVOKED", dedup_hash="b"),
        Finding(artifact_id=a.id, tool="t", rule_id="r3", severity="high",
                message="m", file_path="x.py", status="REVOKED", dedup_hash="c"),
    ])
    await db_session.commit()

    captured = {}
    async def capture_stub(client_, prompt):
        captured["prompt"] = prompt
        return AiSummaryOutput(overview_md="x", top_risks=[], recommendations_md="x")

    svc = SummaryService(llm_caller=capture_stub)
    await svc.generate(db_session, project_id=p.id, run_id=None)

    # Prompt should reference active=1, revoked=2 — NOT total=3 as the
    # primary number.
    assert "total active = 1" in captured["prompt"]
    assert "critical = 1" in captured["prompt"]
    assert "đã revoke từ tổng 3" in captured["prompt"]


def test_pick_diverse_dedups_same_group():
    """V3.4 BUG-3 — 5 findings sharing rule_id family collapse to 1."""
    class F:
        def __init__(self, fid, rule, file, sev="high", tool="trivy"):
            self.id = fid; self.rule_id = rule; self.file_path = file
            self.severity = sev; self.tool = tool

    # All 5 findings target the same Java snakeyaml library
    pool = [
        F(1, "CVE-2022-25857", "Java:org.yaml:snakeyaml"),
        F(2, "CVE-2022-41854", "Java:org.yaml:snakeyaml"),
        F(3, "CVE-2022-38752", "Java:org.yaml:snakeyaml"),
        F(4, "java/path-injection", "src/Foo.java"),
        F(5, "java/ssrf", "src/Bar.java"),
    ]
    diverse = _pick_diverse(pool, k=5)
    # 3 distinct groups → 3 representatives + then fill from remainder
    groups = {_risk_group_key(f) for f in diverse[:3]}
    assert len(groups) == 3, f"expected 3 distinct groups, got {groups}"


def test_risk_group_key_clusters_cves_by_file():
    """CVE rules without slashes cluster by file_path so a library's CVE
    family doesn't dominate the top list."""
    class F:
        def __init__(self, rule, file):
            self.rule_id = rule; self.file_path = file
            self.tool = "trivy"; self.severity = "high"; self.id = 1
    assert _risk_group_key(F("CVE-2022-25857", "Java:org.yaml:snakeyaml")) == \
           _risk_group_key(F("CVE-2022-41854", "Java:org.yaml:snakeyaml"))
    # Different file → different group
    assert _risk_group_key(F("CVE-2022-25857", "Java:org.yaml:snakeyaml")) != \
           _risk_group_key(F("CVE-2022-25857", "Java:io.netty:netty"))


@pytest.mark.asyncio
async def test_pipeline_health_uses_github_conclusions(client, db_session):
    """V3.4 BUG-1 — pass rate must reflect real GitHub conclusion, not
    `runs_total - critical_count`."""
    p = Project(
        name="P", github_url="https://github.com/test/pipe",
        github_owner="o", github_repo="r", github_token="t",
    )
    db_session.add(p)
    await db_session.flush()
    a = Artifact(github_artifact_id="x", project_id=p.id, github_run_id=1, status="processed")
    db_session.add(a)
    await db_session.flush()
    # 10 critical findings — with the old crude formula this would have
    # produced runs_passed=1 and a 9.1% pass rate. The fix should ignore
    # the finding count and trust GitHub.
    for i in range(10):
        db_session.add(Finding(
            artifact_id=a.id, tool="t", rule_id=f"r{i}", severity="critical",
            message="m", file_path="x.py", status="pending_review",
            dedup_hash=f"d{i}",
        ))
    await db_session.commit()

    fake_runs = [
        {"id": i, "conclusion": "success"} for i in range(9)
    ] + [{"id": 99, "conclusion": "failure"}]

    async def stub_llm(c, prompt):
        return AiSummaryOutput(overview_md="x", top_risks=[], recommendations_md="x")

    with patch("src.services.github_client.GitHubClient.list_workflow_runs",
               new=AsyncMock(return_value=fake_runs)):
        svc = SummaryService(llm_caller=stub_llm)
        r = await svc.generate(db_session, project_id=p.id, run_id=None)

    assert r.pipeline_health.runs_total == 10
    assert r.pipeline_health.runs_passed == 9
    assert r.pipeline_health.pass_rate_pct == 90.0
    assert r.pipeline_health.trend == "stable"


@pytest.mark.asyncio
async def test_pipeline_health_falls_back_when_github_errors(client, db_session):
    """When GitHub API is unreachable, pipeline_health is honest about
    not knowing pass rate — runs_passed=0, trend='stable' (insufficient data)."""
    p = Project(
        name="P", github_url="https://github.com/test/pipe-err",
        github_owner="o", github_repo="r", github_token="t",
    )
    db_session.add(p)
    await db_session.flush()
    a = Artifact(github_artifact_id="y", project_id=p.id, github_run_id=42, status="processed")
    db_session.add(a)
    await db_session.flush()
    db_session.add(Finding(
        artifact_id=a.id, tool="t", rule_id="r", severity="high",
        message="m", file_path="x.py", status="pending_review", dedup_hash="zz",
    ))
    await db_session.commit()

    async def stub_llm(c, prompt):
        return AiSummaryOutput(overview_md="x", top_risks=[], recommendations_md="x")

    with patch("src.services.github_client.GitHubClient.list_workflow_runs",
               new=AsyncMock(side_effect=RuntimeError("network down"))):
        svc = SummaryService(llm_caller=stub_llm)
        r = await svc.generate(db_session, project_id=p.id, run_id=None)

    # Fallback path uses local artifact count; pass rate = 0 (unknown), not a lie
    assert r.pipeline_health.runs_total == 1
    assert r.pipeline_health.runs_passed == 0
    assert r.pipeline_health.pass_rate_pct == 0.0


@pytest.mark.asyncio
async def test_summary_endpoint_returns_json(client, db_session, monkeypatch):
    p = Project(name="EP", github_url="https://github.com/test/ep")
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    await _seed_findings(db_session, p, n_critical=1, n_high=2)

    # Replace the SummaryService LLM call site so the live endpoint test
    # doesn't hit Gemini.
    from src.services.llm import summary as summary_mod
    async def stub(client, prompt):
        return AiSummaryOutput(
            overview_md="Endpoint test", top_risks=[],
            recommendations_md="1. Triage",
        )
    monkeypatch.setattr(summary_mod, "_call_gemini_summary", stub)

    resp = await client.get(f"/findings/ai-summary?project_id={p.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == p.id
    assert body["overview_md"] == "Endpoint test"
    # pipeline_health is sourced from the GitHub stub which returns [] in
    # this test fixture — runs_total=0 is the truthful answer, not >= 1.
    assert body["pipeline_health"]["runs_total"] == 0
    assert "trend" in body["pipeline_health"]

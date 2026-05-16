"""V3.3 Part B — AI summary endpoint tests.

LLM call is stubbed so tests are deterministic and don't burn quota. The
caching, fallback (empty project), and force_refresh paths are covered.
"""
import pytest

from src.models.entities import Artifact, Finding, Project
from src.services.llm.summary import (
    AiSummaryOutput,
    SummaryService,
    TopRisk,
    clear_cache,
)


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
    r = await svc.generate(db_session, project_id=p.id, run_id=None)
    assert r.overview_md == "Test overview"
    assert r.recommendations_md == "1. Fix it"
    assert len(r.top_risks) == 1
    assert r.top_risks[0].severity == "critical"
    assert r.pipeline_health.runs_total >= 1


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
    assert body["pipeline_health"]["runs_total"] >= 1
    assert "trend" in body["pipeline_health"]

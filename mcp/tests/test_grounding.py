"""V4.2 — anti-hallucination grounding check for AI fix diffs + /findings/ai-stats."""
from src.core.db import AsyncSessionLocal
from src.models.entities import Artifact, Finding, Project
from src.models.schemas import InvestigationStep
from src.services.llm.service import (
    verify_diff_grounding,
    verify_investigation_grounding,
)

SRC = "def handler(req):\n    q = req.args.get('id')\n    cur.execute('SELECT * FROM u WHERE id=' + q)\n    return q\n"


def test_grounded_diff_passes():
    diff = (
        "@@ -3,1 +3,1 @@\n"
        "-    cur.execute('SELECT * FROM u WHERE id=' + q)\n"
        "+    cur.execute('SELECT * FROM u WHERE id=%s', (q,))\n"
    )
    grounded, note = verify_diff_grounding(diff, SRC)
    assert grounded is True


def test_hallucinated_diff_fails():
    # anchor/removed lines reference code that isn't in SRC at all.
    diff = (
        "@@ -10,2 +10,2 @@\n"
        "-    password = decrypt(secret_vault.fetch('db'))\n"
        "-    conn = mysql.connect(password)\n"
        "+    conn = mysql.connect(get_secret())\n"
    )
    grounded, note = verify_diff_grounding(diff, SRC)
    assert grounded is False
    assert "neo" in note


def test_no_source_is_not_grounded():
    grounded, _ = verify_diff_grounding("- x = 1\n+ x = 2\n", None)
    assert grounded is False


def test_pure_addition_is_grounded_na():
    grounded, note = verify_diff_grounding("@@ -0,0 +1,2 @@\n+import os\n+x = 1\n", SRC)
    assert grounded is True


# ---------------------------------------------------------------------------
# V4.3 — investigation evidence grounding
# ---------------------------------------------------------------------------

def _step(quote, ls=0, le=0):
    return InvestigationStep(claim_vi="c", file="f.py", line_start=ls, line_end=le, quote=quote)


def test_investigation_grounded_quote_passes():
    steps = [_step("cur.execute('SELECT * FROM u WHERE id=' + q)", ls=3, le=3)]
    per_step, overall, note = verify_investigation_grounding(steps, SRC)
    assert per_step[0][0] is True
    assert overall is True


def test_investigation_hallucinated_quote_flagged():
    steps = [_step("password = decrypt(secret_vault.fetch('db'))", ls=10, le=10)]
    per_step, overall, note = verify_investigation_grounding(steps, SRC)
    assert per_step[0][0] is False
    assert overall is False
    assert "bịa" in per_step[0][1]


def test_investigation_line_mismatch_weak_fallback():
    # quote IS in the source but the cited line number is wrong -> weak fallback
    steps = [_step("q = req.args.get('id')", ls=99, le=99)]
    per_step, overall, _ = verify_investigation_grounding(steps, SRC)
    assert per_step[0][0] is True
    assert "lệch dòng" in per_step[0][1]
    assert overall is True


def test_investigation_no_source_all_ungrounded():
    steps = [_step("q = req.args.get('id')", ls=2, le=2)]
    per_step, overall, note = verify_investigation_grounding(steps, None)
    assert per_step[0][0] is False
    assert overall is False


def test_investigation_no_citations_not_grounded():
    # steps with no real code quote -> nothing to verify -> overall not grounded
    steps = [InvestigationStep(claim_vi="mơ hồ", quote="")]
    per_step, overall, note = verify_investigation_grounding(steps, SRC)
    assert overall is False


async def test_ai_stats_endpoint(client):
    async with AsyncSessionLocal() as s:
        p = Project(name="AI", github_url="https://github.com/x/ai")
        s.add(p)
        await s.commit()
        await s.refresh(p)
        a = Artifact(github_artifact_id="1", project_id=p.id,
                     github_run_id=900, status="processed")
        s.add(a)
        await s.commit()
        await s.refresh(a)

        def _f(rule, sev, ai, status="ai_analyzed", revoked_by=None):
            return Finding(
                artifact_id=a.id, project_id=p.id, tool="semgrep", rule_id=rule,
                severity=sev, message="m", file_path="f.py", status=status,
                ai_analysis=ai, revoked_by=revoked_by,
            )
        s.add_all([
            _f("r1", "high", {"false_positive_likelihood": "HIGH",
                              "false_positive_reason": "input đã sanitize", "grounded": True}),
            _f("r2", "high", {"false_positive_likelihood": "LOW", "grounded": False}),
            _f("r3", "medium", {"false_positive_likelihood": "LOW", "grounded": True}),
            _f("r4", "high", None, status="REVOKED", revoked_by="ai-triage (by alice)"),
        ])
        await s.commit()
        pid = p.id

    r = await client.get("/findings/ai-stats", params={"project_id": pid, "run_id": 900})
    assert r.status_code == 200
    d = r.json()
    assert d["analyzed"] == 3
    assert d["fp_likelihood"]["HIGH"] == 1
    assert d["grounded"] == 2 and d["ungrounded"] == 1
    assert d["ai_revoked"] == 1
    assert len(d["top_false_positive"]) == 1
    assert d["top_false_positive"][0]["reason"] == "input đã sanitize"

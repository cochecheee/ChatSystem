"""V3.3 Part A — auth hardening tests.

Verifies the ANONYMOUS_READ_ENABLED kill-switch gates every read endpoint
when off, and authed callers still pass through.
"""
from unittest.mock import patch

import pytest

from src.models.entities import Artifact, Finding, Project

READ_ENDPOINTS_NO_PATH = [
    "/projects",
    "/findings",
    "/stats/overview",
    "/stats/latest-scan",
    "/stats/runs?days=7",
    "/github/runs",
]


from tests.conftest import issue_token


async def _token(client, username="alice", role="developer") -> str:
    return await issue_token(client, username, role)


def _patch_anonymous(enabled: bool):
    """Override ANONYMOUS_READ_ENABLED on the live settings object.

    Patching the imported `settings` module-level object affects every
    place that does `from .config import settings` then `settings.X`.
    """
    from src.core import config as cfg
    return patch.object(cfg.settings, "ANONYMOUS_READ_ENABLED", enabled)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", READ_ENDPOINTS_NO_PATH)
async def test_anonymous_blocked_when_flag_off(client, path):
    """V3.3 default — every read endpoint returns 401 without a JWT."""
    with _patch_anonymous(False):
        resp = await client.get(path)
        assert resp.status_code == 401, f"{path} should require auth, got {resp.status_code}"


@pytest.mark.asyncio
@pytest.mark.parametrize("path", READ_ENDPOINTS_NO_PATH)
async def test_anonymous_allowed_when_flag_on(client, path):
    """Legacy bypass — flag on lets anonymous through (V2.x behavior)."""
    with _patch_anonymous(True):
        resp = await client.get(path)
        # Some paths 404 with empty DB (latest-scan returns 200 with run_id=null,
        # /findings/{id} not present here). Just verify NOT a 401.
        assert resp.status_code != 401, f"{path} should be open, got 401"


@pytest.mark.asyncio
async def test_authed_passes_when_flag_off(client):
    """With JWT attached, all read endpoints respond 2xx."""
    token = await _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    with _patch_anonymous(False):
        for path in READ_ENDPOINTS_NO_PATH:
            resp = await client.get(path, headers=headers)
            assert resp.status_code != 401, f"{path} 401 even with token"


@pytest.mark.asyncio
async def test_gate_count_accepts_jwt(client):
    """gate-count: JWT works (dashboard caller)."""
    token = await _token(client)
    with _patch_anonymous(False):
        resp = await client.get(
            "/findings/gate-count",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_gate_count_accepts_ci_webhook_token(client):
    """gate-count: CI_WEBHOOK_TOKEN works (Security Gate composite caller)."""
    from src.core import config as cfg
    secret = "test-ci-secret"
    with _patch_anonymous(False), \
         patch.object(cfg.settings, "CI_WEBHOOK_TOKEN", secret):
        resp = await client.get(
            "/findings/gate-count",
            headers={"Authorization": f"Bearer {secret}"},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_gate_count_rejects_wrong_token(client):
    """gate-count: random bearer != CI token and != JWT → 401."""
    from src.core import config as cfg
    with _patch_anonymous(False), \
         patch.object(cfg.settings, "CI_WEBHOOK_TOKEN", "real-secret"):
        resp = await client.get(
            "/findings/gate-count",
            headers={"Authorization": "Bearer not-the-secret"},
        )
        assert resp.status_code == 401


def _patch_rbac(enabled: bool):
    from src.core import config as cfg
    return patch.object(cfg.settings, "RBAC_PER_PROJECT", enabled)


@pytest.mark.asyncio
async def test_findings_filtered_by_user_memberships(client, db_session):
    """V3.3 A.3 — RBAC on + non-admin sees only findings from their projects."""
    # Two projects with one finding each
    p1 = Project(name="P1", github_url="https://github.com/test/p1")
    p2 = Project(name="P2", github_url="https://github.com/test/p2")
    db_session.add_all([p1, p2])
    await db_session.flush()
    a1 = Artifact(github_artifact_id="a1", project_id=p1.id, status="processed")
    a2 = Artifact(github_artifact_id="a2", project_id=p2.id, status="processed")
    db_session.add_all([a1, a2])
    await db_session.flush()
    db_session.add_all([
        Finding(artifact_id=a1.id, project_id=p1.id, tool="t", rule_id="r1", severity="high",
                message="m", file_path="x.py", status="pending_review", dedup_hash="ph1"),
        Finding(artifact_id=a2.id, project_id=p2.id, tool="t", rule_id="r2", severity="high",
                message="m", file_path="y.py", status="pending_review", dedup_hash="ph2"),
    ])
    await db_session.commit()

    # Seed: alice is owner of p1 only
    admin_tok = await _token(client, "root", role="admin")
    r = await client.post(
        f"/projects/{p1.id}/members",
        json={"username": "alice", "role": "owner"},
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert r.status_code == 201

    alice_tok = await _token(client, "alice", role="developer")
    with _patch_anonymous(False), _patch_rbac(True):
        # No project_id specified → server should filter to p1 only
        listed = (await client.get(
            "/findings", headers={"Authorization": f"Bearer {alice_tok}"},
        )).json()
        assert len(listed) == 1
        assert listed[0]["project_id"] == p1.id

        # Explicit project_id matching membership → allowed
        ok = await client.get(
            f"/findings?project_id={p1.id}",
            headers={"Authorization": f"Bearer {alice_tok}"},
        )
        assert ok.status_code == 200

        # Explicit project_id NOT in memberships → 403
        denied = await client.get(
            f"/findings?project_id={p2.id}",
            headers={"Authorization": f"Bearer {alice_tok}"},
        )
        assert denied.status_code == 403


@pytest.mark.asyncio
async def test_github_runs_denied_for_non_member_project(client, project):
    """V3.3 A.3 — /github/runs?project_id=X for non-member → 403."""
    bob_tok = await _token(client, "bob", role="developer")
    with _patch_anonymous(False), _patch_rbac(True):
        resp = await client.get(
            f"/github/runs?project_id={project['id']}",
            headers={"Authorization": f"Bearer {bob_tok}"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_path_params_also_gated(client, db_session):
    """Path-param routes (/findings/{id}, /github/runs/{id}/findings) are gated too."""
    p = Project(name="P", github_url="https://github.com/test/gated")
    db_session.add(p)
    await db_session.flush()
    a = Artifact(github_artifact_id="x", project_id=p.id, github_run_id=42, status="processed")
    db_session.add(a)
    await db_session.flush()
    db_session.add(Finding(
        artifact_id=a.id, tool="t", rule_id="r", severity="high",
        message="m", file_path="x.py", status="pending_review",
        dedup_hash="auth-gate-hash",
    ))
    await db_session.commit()

    fid = (await client.get("/findings")).json()[0]["id"]
    with _patch_anonymous(False):
        anon = await client.get(f"/findings/{fid}")
        assert anon.status_code == 401

        anon_run = await client.get("/github/runs/42/findings")
        assert anon_run.status_code == 401

        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}"}
        authed = await client.get(f"/findings/{fid}", headers=headers)
        assert authed.status_code == 200

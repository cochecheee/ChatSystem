"""V3.6 — HMAC signature verify + WebhookDelivery dedup smoke tests."""
from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest

from src.core.auth import create_access_token


def _admin() -> dict:
    return {"Authorization": f"Bearer {create_access_token('root', 'admin')}"}


def _sign(body: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


@pytest.fixture(autouse=True)
def _stub_processor():
    """Webhook auth+routing tests — stub process_run so TestClient inline
    BackgroundTasks executor doesn't try a real GitHub fetch."""
    with patch(
        "src.api.artifacts.SecurityProcessor.process_run",
        new_callable=AsyncMock,
    ) as m:
        yield m


@pytest.mark.asyncio
async def test_hmac_valid_signature_routes_to_owning_project(client, project):
    """Sign body with project A's token → routed to A, ignoring body.repository."""
    pid = project["id"]
    rot = await client.post(f"/projects/{pid}/webhook/rotate", headers=_admin())
    token = rot.json()["webhook_token"]

    body = json.dumps({"run_id": 999, "repository": "other/repo"}).encode("utf-8")
    sig = _sign(body, token)
    resp = await client.post(
        "/webhook/pipeline-complete",
        content=body,
        headers={
            "content-type": "application/json",
            "x-hub-signature-256": sig,
            "x-github-delivery": "test-delivery-1",
        },
    )
    assert resp.status_code == 202, resp.text
    j = resp.json()
    assert j["project_id"] == pid
    assert j["auth_mode"] == "hmac"
    assert j["outcome"] == "accepted"


@pytest.mark.asyncio
async def test_hmac_invalid_signature_returns_403(client, project):
    pid = project["id"]
    await client.post(f"/projects/{pid}/webhook/rotate", headers=_admin())

    body = json.dumps({"run_id": 1}).encode("utf-8")
    # Sign with WRONG secret
    bad_sig = _sign(body, "wrong-secret-xyz")
    resp = await client.post(
        "/webhook/pipeline-complete",
        content=body,
        headers={
            "content-type": "application/json",
            "x-hub-signature-256": bad_sig,
            "x-github-delivery": "test-delivery-bad",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delivery_dedup_skips_replay(client, project):
    pid = project["id"]
    rot = await client.post(f"/projects/{pid}/webhook/rotate", headers=_admin())
    token = rot.json()["webhook_token"]

    body = json.dumps({"run_id": 555}).encode("utf-8")
    sig = _sign(body, token)
    headers = {
        "content-type": "application/json",
        "x-hub-signature-256": sig,
        "x-github-delivery": "replay-delivery-1",
    }
    # First delivery
    r1 = await client.post("/webhook/pipeline-complete", content=body, headers=headers)
    assert r1.status_code == 202
    assert r1.json()["outcome"] == "accepted"
    # Replay same delivery_id → duplicate, not processed twice
    r2 = await client.post("/webhook/pipeline-complete", content=body, headers=headers)
    assert r2.status_code == 202
    assert r2.json()["outcome"] == "duplicate"


@pytest.mark.asyncio
async def test_legacy_bearer_still_works_without_hmac(client, project):
    """V3.5 bearer auth path remains operational for un-migrated CIs."""
    pid = project["id"]
    rot = await client.post(f"/projects/{pid}/webhook/rotate", headers=_admin())
    token = rot.json()["webhook_token"]

    body = json.dumps({"run_id": 777}).encode("utf-8")
    resp = await client.post(
        "/webhook/pipeline-complete",
        content=body,
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {token}",  # no HMAC header
            "x-github-delivery": "bearer-only-1",
        },
    )
    assert resp.status_code == 202
    j = resp.json()
    assert j["project_id"] == pid
    assert j["auth_mode"] == "bearer_per_project"

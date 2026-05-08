"""Tests for config endpoints (Wave 4 — GAP-12/13/14)."""
import pytest

from src.core.auth import create_access_token


def _headers(role: str = "admin") -> dict:
    return {"Authorization": f"Bearer {create_access_token(username=role, role=role)}"}


@pytest.mark.asyncio
async def test_list_config_returns_defaults(client):
    resp = await client.get("/config")
    assert resp.status_code == 200
    body = resp.json()
    assert "sast_tools" in body
    assert "gates" in body
    assert "ai" in body
    # Defaults
    assert body["sast_tools"]["semgrep"] is True
    assert body["gates"]["block_on_critical"] is True
    assert body["ai"]["model"] == "gemini-3.1-pro-preview"


@pytest.mark.asyncio
async def test_get_unknown_key_returns_404(client):
    resp = await client.get("/config/no_such_key")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_config_admin_only(client):
    # Developer không được sửa
    resp = await client.put(
        "/config/sast_tools",
        headers=_headers("developer"),
        json={"semgrep": False},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_config_no_token_returns_401(client):
    resp = await client.put("/config/sast_tools", json={"semgrep": False})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_config_persists(client):
    # Admin update sast_tools.semgrep = False
    resp = await client.put(
        "/config/sast_tools",
        headers=_headers("admin"),
        json={"semgrep": False, "trivy": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["semgrep"] is False
    assert body["trivy"] is False
    # Các field khác giữ default
    assert body["codeql"] is True

    # GET sau khi update thấy đúng
    resp = await client.get("/config/sast_tools")
    assert resp.status_code == 200
    assert resp.json()["semgrep"] is False
    assert resp.json()["trivy"] is False


@pytest.mark.asyncio
async def test_update_config_strips_unknown_fields(client):
    resp = await client.put(
        "/config/gates",
        headers=_headers("admin"),
        json={"block_on_critical": False, "evil_field": "hacker"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["block_on_critical"] is False
    assert "evil_field" not in body


@pytest.mark.asyncio
async def test_update_unknown_key_returns_404(client):
    resp = await client.put(
        "/config/no_such_key",
        headers=_headers("admin"),
        json={"foo": "bar"},
    )
    assert resp.status_code == 404

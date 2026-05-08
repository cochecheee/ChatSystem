"""Config endpoints — runtime dashboard settings."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import User, get_current_user
from ..core.config import settings
from ..core.db import get_session
from ..services.config_service import ConfigService, UnknownConfigKeyError

router = APIRouter(prefix="/config", tags=["config"])


def _require_admin(current_user: User) -> None:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Chỉ admin mới được sửa config.",
        )


@router.get("", summary="Get tất cả config keys")
async def list_config(session: AsyncSession = Depends(get_session)) -> dict[str, dict[str, Any]]:
    """Trả về toàn bộ config (sast_tools, gates, ai). Public — không cần auth."""
    return await ConfigService(session).get_all()


@router.get("/integrations", summary="External integrations status")
async def get_integrations() -> dict[str, dict[str, Any]]:
    """Trả về status của các integrations external (GitHub, Gemini, CI hooks).

    KHÔNG trả ra giá trị secret — chỉ boolean configured + metadata public.
    """
    return {
        "github": {
            "configured": bool(settings.GITHUB_TOKEN and settings.GITHUB_OWNER and settings.GITHUB_REPO),
            "owner": settings.GITHUB_OWNER or None,
            "repo": settings.GITHUB_REPO or None,
            "polling_interval_seconds": settings.POLLING_INTERVAL_SECONDS,
        },
        "gemini": {
            "configured": bool(settings.GEMINI_API_KEY),
            "model": settings.GEMINI_MODEL,
        },
        "ci_ingest": {
            "api_key_required": bool(settings.CI_API_KEY),
            "webhook_token_required": bool(settings.CI_WEBHOOK_TOKEN),
        },
    }


@router.get("/{key}", summary="Get 1 config key")
async def get_config(
    key: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        return await ConfigService(session).get(key)
    except UnknownConfigKeyError:
        raise HTTPException(status_code=404, detail=f"Config key không hợp lệ: {key}")


@router.put("/{key}", summary="Update 1 config key (admin only)")
async def update_config(
    key: str,
    value: dict[str, Any],
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_admin(current_user)
    try:
        return await ConfigService(session).update(key, value)
    except UnknownConfigKeyError:
        raise HTTPException(status_code=404, detail=f"Config key không hợp lệ: {key}")

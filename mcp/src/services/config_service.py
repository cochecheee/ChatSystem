"""Config service — wrap ConfigRepository với defaults + validation per key."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories import ConfigRepository

# ---------------------------------------------------------------------------
# Defaults — schema cho từng config key.
# Khi dashboard request key chưa có trong DB, trả default này.
# ---------------------------------------------------------------------------

DEFAULTS: dict[str, dict[str, Any]] = {
    "sast_tools": {
        "semgrep":          True,
        "codeql":           True,
        "spotbugs":         True,
        "eslint":           True,
        "trivy":            True,
        "dependency_check": True,
    },
    "gates": {
        "block_on_critical":    True,
        "block_on_high":        False,
        "block_on_secrets":     True,
        "min_cvss_score":       7.0,
        "require_ai_analysis":  False,
    },
    "ai": {
        "auto_analyze_critical":    True,
        "auto_analyze_high":        False,
        "model":                    "gemini-3.1-pro-preview",
        "max_findings_per_run":     50,
        "include_source_context":   True,
    },
}

KNOWN_KEYS = set(DEFAULTS.keys())


class UnknownConfigKeyError(ValueError):
    """Key không thuộc DEFAULTS — service từ chối lưu để tránh dirty data."""


class ConfigService:
    def __init__(self, session: AsyncSession):
        self.repo = ConfigRepository(session)

    async def get(self, key: str) -> dict[str, Any]:
        if key not in KNOWN_KEYS:
            raise UnknownConfigKeyError(key)
        stored = await self.repo.get(key)
        # Merge stored on top of defaults — đảm bảo field mới được thêm vào DEFAULTS
        # vẫn xuất hiện cho client cũ.
        return {**DEFAULTS[key], **(stored or {})}

    async def get_all(self) -> dict[str, dict[str, Any]]:
        stored = await self.repo.list_all()
        return {
            key: {**DEFAULTS[key], **(stored.get(key, {}))}
            for key in KNOWN_KEYS
        }

    async def update(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        if key not in KNOWN_KEYS:
            raise UnknownConfigKeyError(key)
        # Validate: chỉ cho phép update fields có trong DEFAULTS để tránh client
        # gửi field lạ làm dirty schema.
        allowed = set(DEFAULTS[key].keys())
        sanitized = {k: v for k, v in value.items() if k in allowed}
        # Merge với stored hiện tại (partial update)
        current = await self.repo.get(key) or {}
        merged = {**current, **sanitized}
        await self.repo.upsert(key, merged)
        return {**DEFAULTS[key], **merged}

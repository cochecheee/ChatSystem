"""AppConfig repository — key-value store cho runtime config."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.entities import AppConfig


class ConfigRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, key: str) -> dict[str, Any] | None:
        row = await self.session.get(AppConfig, key)
        return row.value if row else None

    async def list_all(self) -> dict[str, dict[str, Any]]:
        result = await self.session.execute(select(AppConfig))
        return {row.key: row.value for row in result.scalars().all()}

    async def upsert(self, key: str, value: dict[str, Any]) -> dict[str, Any]:
        existing = await self.session.get(AppConfig, key)
        if existing is None:
            row = AppConfig(key=key, value=value)
            self.session.add(row)
        else:
            existing.value = value
        await self.session.commit()
        return value

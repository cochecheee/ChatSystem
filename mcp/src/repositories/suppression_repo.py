"""V3.1 Tier 2 — repository for SuppressionRule."""
from __future__ import annotations

import fnmatch
from datetime import datetime, UTC

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.entities import SuppressionRule


# Ordered low → high, mirrors finding.severity values used elsewhere.
SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _severity_le(actual: str, ceiling: str) -> bool:
    return SEVERITY_RANK.get(actual, 99) <= SEVERITY_RANK.get(ceiling, -1)


def rule_matches(
    rule: SuppressionRule,
    *,
    finding_rule_id: str,
    finding_file_path: str,
    finding_tool: str,
    finding_severity: str,
) -> bool:
    """All non-null fields on rule must match the finding."""
    if rule.expires_at is not None and rule.expires_at < datetime.now(UTC):
        return False
    if rule.rule_id is not None and rule.rule_id != finding_rule_id:
        return False
    if rule.tool is not None and rule.tool != finding_tool:
        return False
    if rule.severity_max is not None and not _severity_le(finding_severity, rule.severity_max):
        return False
    if rule.file_glob is not None and not fnmatch.fnmatch(finding_file_path, rule.file_glob):
        return False
    return True


class SuppressionRuleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_active_for_project(self, project_id: int) -> list[SuppressionRule]:
        """Active rules = not-yet-expired rules for this project."""
        now = datetime.now(UTC)
        query = (
            select(SuppressionRule)
            .where(SuppressionRule.project_id == project_id)
            .where(or_(SuppressionRule.expires_at.is_(None), SuppressionRule.expires_at > now))
            .order_by(SuppressionRule.id.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_all_for_project(self, project_id: int) -> list[SuppressionRule]:
        result = await self.session.execute(
            select(SuppressionRule)
            .where(SuppressionRule.project_id == project_id)
            .order_by(SuppressionRule.id.desc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        *,
        project_id: int,
        reason: str,
        created_by: str,
        rule_id: str | None = None,
        file_glob: str | None = None,
        tool: str | None = None,
        severity_max: str | None = None,
        expires_at: datetime | None = None,
    ) -> SuppressionRule:
        rule = SuppressionRule(
            project_id=project_id,
            reason=reason,
            created_by=created_by,
            rule_id=rule_id,
            file_glob=file_glob,
            tool=tool,
            severity_max=severity_max,
            expires_at=expires_at,
        )
        self.session.add(rule)
        await self.session.commit()
        await self.session.refresh(rule)
        return rule

    async def get(self, rule_id: int) -> SuppressionRule | None:
        return await self.session.get(SuppressionRule, rule_id)

    async def delete(self, rule_id: int) -> bool:
        result = await self.session.execute(
            delete(SuppressionRule).where(SuppressionRule.id == rule_id)
        )
        await self.session.commit()
        return (result.rowcount or 0) > 0

"""Abstract base class shared by every tool normalizer."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ...models.schemas import FindingCreate, compute_dedup_hash


class BaseNormalizer(ABC):
    TOOL_NAME: str = "unknown"

    @abstractmethod
    def normalize(self, content: str, artifact_id: int) -> list[FindingCreate]:
        """Parse raw content and return normalised findings."""

    def deduplicate(
        self,
        findings: list[FindingCreate],
        existing_hashes: set[str],
    ) -> list[FindingCreate]:
        """Remove findings whose dedup hash already exists."""
        seen: set[str] = set()
        result: list[FindingCreate] = []
        for f in findings:
            h = compute_dedup_hash(f.rule_id, f.file_path, f.message)
            if h not in existing_hashes and h not in seen:
                seen.add(h)
                result.append(f)
        return result

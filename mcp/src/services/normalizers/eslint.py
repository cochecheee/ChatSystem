"""ESLint JSON normalizer.

Legacy format — the current pipeline emits ESLint results as .sarif, but this
is kept to support older pipelines or custom formatters.
"""
from __future__ import annotations

import json

from ...models.schemas import FindingCreate, compute_dedup_hash
from .base import BaseNormalizer
from .severity import _ESLINT_SEVERITY_TO_SEVERITY, resolve_severity


class ESLintNormalizer(BaseNormalizer):
    TOOL_NAME = "eslint"

    def normalize(self, content: str, artifact_id: int) -> list[FindingCreate]:
        data = json.loads(content)
        findings: list[FindingCreate] = []

        if not isinstance(data, list) or not data:
            return findings

        for file_result in data:
            if not isinstance(file_result, dict):
                continue
            file_path = file_result.get("filePath", "unknown")
            for msg in file_result.get("messages", []):
                rule_id = msg.get("ruleId") or "unknown-rule"
                eslint_sev = msg.get("severity", 1)
                res = resolve_severity(
                    label_band=_ESLINT_SEVERITY_TO_SEVERITY.get(eslint_sev),
                    raw_label=f"eslint={eslint_sev}",
                )
                severity = res.severity
                message = msg.get("message", "")
                line_number = msg.get("line")

                dedup = compute_dedup_hash(rule_id, file_path, message)
                findings.append(
                    FindingCreate(
                        artifact_id=artifact_id,
                        tool=self.TOOL_NAME,
                        rule_id=rule_id,
                        severity=severity,
                        message=message,
                        file_path=file_path,
                        line_number=line_number,
                        raw_data={
                            "column": msg.get("column"),
                            "dedup_hash": dedup,
                            "_severity": res.provenance(),
                        },
                    )
                )

        return findings

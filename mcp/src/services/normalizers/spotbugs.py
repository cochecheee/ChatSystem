"""SpotBugs / Find Security Bugs XML report normalizer."""
from __future__ import annotations

import defusedxml.ElementTree as ET

from ...models.schemas import FindingCreate, compute_dedup_hash
from .base import BaseNormalizer
from .severity import _SPOTBUGS_PRIORITY_TO_SEVERITY, resolve_severity


class SpotBugsXMLNormalizer(BaseNormalizer):
    TOOL_NAME = "spotbugs"

    def normalize(self, content: str, artifact_id: int) -> list[FindingCreate]:
        root = ET.fromstring(content)  # defusedxml — Billion Laughs safe
        findings: list[FindingCreate] = []

        for bug in root.iter("BugInstance"):
            rule_id = bug.get("type", "unknown")
            priority = bug.get("priority", "3")
            res = resolve_severity(
                label_band=_SPOTBUGS_PRIORITY_TO_SEVERITY.get(priority, "low"),
                raw_label=f"priority={priority}",
            )
            severity = res.severity
            cwe_id = bug.get("cweid")
            cwe_str = f"CWE-{cwe_id}" if cwe_id else None

            short_msg = bug.findtext("ShortMessage") or bug.get("type", "")
            long_msg = bug.findtext("LongMessage") or short_msg
            message = long_msg or short_msg

            source = bug.find("SourceLine")
            if source is not None:
                file_path = source.get("sourcepath") or source.get("classname") or "unknown"
                line_str = source.get("start")
                line_number = int(line_str) if line_str and line_str.isdigit() else None
            else:
                file_path = "unknown"
                line_number = None

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
                    cwe_id=cwe_str,
                    raw_data={
                        "category": bug.get("category"),
                        "rank": bug.get("rank"),
                        "dedup_hash": dedup,
                        "_severity": res.provenance(),
                    },
                )
            )

        return findings

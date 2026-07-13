"""Trivy JSON normalizer (trivy-image.json / detailed container scan)."""
from __future__ import annotations

import json

from ...models.schemas import FindingCreate, compute_dedup_hash
from .base import BaseNormalizer
from .severity import resolve_severity


class TrivyJsonNormalizer(BaseNormalizer):
    TOOL_NAME = "trivy"

    def normalize(self, content: str, artifact_id: int) -> list[FindingCreate]:
        data = json.loads(content)
        findings: list[FindingCreate] = []

        for result_entry in data.get("Results", []):
            target = result_entry.get("Target", "unknown")

            for vuln in result_entry.get("Vulnerabilities") or []:
                rule_id = vuln.get("VulnerabilityID") or "unknown-cve"
                sev_raw = vuln.get("Severity", "")
                message = vuln.get("Title") or vuln.get("Description") or rule_id
                cwe_ids: list[str] = vuln.get("CweIDs") or []
                cwe_id = cwe_ids[0] if cwe_ids else None

                cvss_score: float | None = None
                score_kind: str | None = None
                cvss = vuln.get("CVSS") or {}
                if nvd := cvss.get("nvd"):
                    if nvd.get("V3Score") is not None:
                        cvss_score, score_kind = nvd.get("V3Score"), "v3"
                    elif nvd.get("V2Score") is not None:
                        cvss_score, score_kind = nvd.get("V2Score"), "v2"

                res = resolve_severity(raw_label=sev_raw, score=cvss_score, score_kind=score_kind)
                severity = res.severity

                pkg_name = vuln.get("PkgName", "")
                file_path = f"{target}:{pkg_name}" if pkg_name else target

                dedup = compute_dedup_hash(rule_id, file_path, message)
                findings.append(
                    FindingCreate(
                        artifact_id=artifact_id,
                        tool=self.TOOL_NAME,
                        rule_id=rule_id,
                        severity=severity,
                        message=message,
                        file_path=file_path,
                        line_number=None,
                        cwe_id=cwe_id,
                        cvss_score=res.cvss_score,
                        raw_data={
                            "pkg_name": pkg_name,
                            "installed_version": vuln.get("InstalledVersion"),
                            "fixed_version": vuln.get("FixedVersion"),
                            "dedup_hash": dedup,
                            "_severity": res.provenance(),
                        },
                    )
                )

        return findings

"""OWASP Dependency-Check JSON normalizer (dep-check-report artifact)."""
from __future__ import annotations

import json
import re

from ...models.schemas import FindingCreate, compute_dedup_hash
from .base import BaseNormalizer
from .severity import _sca_severity


def _parse_purl_version(purl: str) -> str | None:
    """Extract version from a Package URL string: pkg:ecosystem/group/artifact@version"""
    match = re.search(r"@([^?#]+)", purl)
    return match.group(1) if match else None


class DepCheckNormalizer(BaseNormalizer):
    TOOL_NAME = "dependency-check"

    def normalize(self, content: str, artifact_id: int) -> list[FindingCreate]:
        data = json.loads(content)
        findings: list[FindingCreate] = []

        for dep in data.get("dependencies", []):
            file_path = dep.get("fileName") or dep.get("filePath") or "unknown"

            # Extract package version from PURL (packages[].id)
            pkg_name: str = dep.get("fileName", "")
            installed_version: str | None = None
            for pkg in dep.get("packages") or []:
                pkg_id = pkg.get("id", "")
                if pkg_id:
                    installed_version = _parse_purl_version(pkg_id)
                    break

            for vuln in dep.get("vulnerabilities", []):
                rule_id = vuln.get("name") or "unknown-cve"
                sev_raw = vuln.get("severity", "")
                message = vuln.get("description") or rule_id
                cwes: list[str] = vuln.get("cwes") or []
                cwe_id = cwes[0] if cwes else None

                cvss_score: float | None = None
                if cvssv3 := vuln.get("cvssv3"):
                    cvss_score = cvssv3.get("baseScore")
                elif cvssv2 := vuln.get("cvssv2"):
                    cvss_score = cvssv2.get("score")

                severity = _sca_severity(sev_raw, cvss_score)

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
                        cvss_score=cvss_score,
                        raw_data={
                            "source": vuln.get("source"),
                            "pkg_name": pkg_name,
                            "installed_version": installed_version,
                            "fixed_version": None,  # DepCheck JSON does not include a fixed version
                            "dedup_hash": dedup,
                        },
                    )
                )

        return findings

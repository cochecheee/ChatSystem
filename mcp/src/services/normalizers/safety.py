"""Safety JSON normalizer (safety.json — Python dependency CVEs)."""
from __future__ import annotations

import json

from ...models.schemas import FindingCreate, compute_dedup_hash
from .base import BaseNormalizer
from .severity import resolve_severity


class SafetyJsonNormalizer(BaseNormalizer):
    """Parse `safety check --json` output (Python SCA).

    Handles both the modern dict shape ({"vulnerabilities": [ {package_name,
    vulnerable_spec, analyzed_version, advisory, vulnerability_id, CVE, ...} ]})
    and the legacy v1 list-of-lists ([[pkg, spec, installed, advisory, id]]).
    """

    TOOL_NAME = "safety"

    def normalize(self, content: str, artifact_id: int) -> list[FindingCreate]:
        data = json.loads(content)
        rows: list = []
        if isinstance(data, dict):
            rows = data.get("vulnerabilities") or data.get("affected_packages") or []
        elif isinstance(data, list):
            rows = data

        findings: list[FindingCreate] = []
        for v in rows:
            if isinstance(v, dict):
                pkg = v.get("package_name") or v.get("package") or "unknown"
                installed = v.get("analyzed_version") or v.get("installed_version")
                spec = v.get("vulnerable_spec") or v.get("vulnerable_versions") or ""
                vid = (v.get("vulnerability_id") or v.get("id")
                       or v.get("CVE") or f"safety-{pkg}")
                advisory = v.get("advisory") or v.get("description") or str(vid)
                cve = v.get("CVE")
                sev_raw = v.get("severity") or ""
            elif isinstance(v, (list, tuple)):
                pkg = v[0] if len(v) > 0 else "unknown"
                spec = v[1] if len(v) > 1 else ""
                installed = v[2] if len(v) > 2 else None
                advisory = v[3] if len(v) > 3 else ""
                vid = v[4] if len(v) > 4 else f"safety-{pkg}"
                cve, sev_raw = None, ""
            else:
                continue

            rule_id = str(vid)
            res = resolve_severity(raw_label=str(sev_raw) or None)
            severity = res.severity
            message = (str(advisory).strip() or rule_id)[:2000]
            file_path = f"requirements.txt:{pkg}"
            dedup = compute_dedup_hash(rule_id, file_path, message)
            findings.append(FindingCreate(
                artifact_id=artifact_id, tool=self.TOOL_NAME, rule_id=rule_id,
                severity=severity, message=message, file_path=file_path,
                line_number=None, cwe_id=None, cvss_score=None,
                raw_data={"pkg_name": pkg, "installed_version": installed,
                          "fixed_version": None, "vulnerable_spec": spec,
                          "cve": cve, "dedup_hash": dedup,
                          "_severity": res.provenance()},
            ))

        return findings

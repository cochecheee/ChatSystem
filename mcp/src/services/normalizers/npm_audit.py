"""npm audit JSON normalizer (npm-audit.json — Node.js SCA)."""
from __future__ import annotations

import json

from ...models.schemas import FindingCreate, compute_dedup_hash
from .base import BaseNormalizer
from .severity import resolve_severity


class NpmAuditNormalizer(BaseNormalizer):
    """Parse `npm audit --json` (auditReportVersion 2; npm 7+).

    Each entry in `vulnerabilities` is keyed by package name. Its `via` array
    holds either advisory objects (the actual CVE/GHSA) or strings naming the
    upstream package that introduces the vuln (transitive). We emit one finding
    per advisory object; packages vulnerable only transitively get one rollup
    finding so they still surface on the dashboard.
    """

    TOOL_NAME = "npm-audit"

    def normalize(self, content: str, artifact_id: int) -> list[FindingCreate]:
        data = json.loads(content)
        findings: list[FindingCreate] = []
        vulns = data.get("vulnerabilities")
        if not isinstance(vulns, dict):
            return findings

        for pkg_name, entry in vulns.items():
            if not isinstance(entry, dict):
                continue
            pkg_sev = (entry.get("severity") or "").lower()
            pkg_range = entry.get("range") or ""
            fix = entry.get("fixAvailable")
            fixed_version = fix.get("version") if isinstance(fix, dict) else None
            vias = entry.get("via") or []
            advisories = [v for v in vias if isinstance(v, dict)]

            if not advisories:
                # Transitive-only: every `via` is a string (upstream pkg name).
                res = resolve_severity(raw_label=pkg_sev or None)
                severity = res.severity
                rule_id = f"npm-audit-{pkg_name}"
                upstream = ", ".join(str(v) for v in vias) or "transitive dependency"
                message = f"{pkg_name} {pkg_range}: vulnerable via {upstream}"
                file_path = f"package-lock.json:{pkg_name}"
                dedup = compute_dedup_hash(rule_id, file_path, message)
                findings.append(FindingCreate(
                    artifact_id=artifact_id, tool=self.TOOL_NAME, rule_id=rule_id,
                    severity=severity, message=message, file_path=file_path,
                    line_number=None, cwe_id=None, cvss_score=None,
                    raw_data={"pkg_name": pkg_name, "installed_version": None,
                              "fixed_version": fixed_version, "range": pkg_range,
                              "dedup_hash": dedup, "_severity": res.provenance()},
                ))
                continue

            for adv in advisories:
                title = adv.get("title") or f"Vulnerability in {pkg_name}"
                url = adv.get("url") or ""
                ghsa = url.rsplit("/", 1)[-1] if "advisories" in url else ""
                source = adv.get("source")
                rule_id = ghsa or (str(source) if source else f"npm-audit-{pkg_name}")
                cwes = adv.get("cwe") or []
                cwe_id = cwes[0] if cwes else None
                cvss = adv.get("cvss") or {}
                cvss_score = cvss.get("score") or None  # npm sends 0 when absent
                via_sev = (adv.get("severity") or pkg_sev or "").lower()
                res = resolve_severity(raw_label=via_sev or None, score=cvss_score, score_kind="v3")
                severity = res.severity
                adv_range = adv.get("range") or pkg_range
                message = f"{title} ({pkg_name} {adv_range})".strip()
                file_path = f"package-lock.json:{pkg_name}"
                dedup = compute_dedup_hash(rule_id, file_path, message)
                findings.append(FindingCreate(
                    artifact_id=artifact_id, tool=self.TOOL_NAME, rule_id=rule_id,
                    severity=severity, message=message, file_path=file_path,
                    line_number=None, cwe_id=cwe_id, cvss_score=res.cvss_score,
                    raw_data={"pkg_name": pkg_name, "installed_version": None,
                              "fixed_version": fixed_version, "range": adv_range,
                              "advisory_url": url, "source": source,
                              "dedup_hash": dedup, "_severity": res.provenance()},
                ))

        return findings

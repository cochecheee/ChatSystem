"""OWASP ZAP baseline/full-scan JSON normalizer — DAST findings (V2.3)."""
from __future__ import annotations

import json

from ...models.schemas import FindingCreate, compute_dedup_hash
from .base import BaseNormalizer
from .severity import _CRITICAL_CWE_IDS


class ZapJsonNormalizer(BaseNormalizer):
    """OWASP ZAP baseline/full-scan JSON report — V2.3 DAST findings.

    ZAP riskcode mapping:  0=Informational  1=Low  2=Medium  3=High
    We emit 1 Finding per (alert, instance) so re-occurrences across
    URLs aren't lost. dedup hash uses (rule_id, uri, alert) so the same
    issue at the same URL collapses on rescan.
    """

    TOOL_NAME = "owasp-zap"
    _RISK_TO_SEVERITY: dict[str, str] = {
        "0": "info",
        "1": "low",
        "2": "medium",
        "3": "high",
    }

    def normalize(self, content: str, artifact_id: int) -> list[FindingCreate]:
        data = json.loads(content)
        findings: list[FindingCreate] = []

        for site in data.get("site") or []:
            site_url = site.get("@name", "")
            for alert in site.get("alerts") or []:
                rule_id = alert.get("pluginid") or alert.get("alertRef") or "zap-unknown"
                severity = self._RISK_TO_SEVERITY.get(
                    str(alert.get("riskcode", "")), "medium"
                )
                title = alert.get("alert") or alert.get("name") or rule_id
                description = alert.get("desc", "")
                solution = alert.get("solution", "")
                cwe_raw = alert.get("cweid")
                cwe_id = f"CWE-{cwe_raw}" if cwe_raw and cwe_raw != "-1" else None

                # Promote DAST high→critical for injection/RCE CWE classes when
                # ZAP itself reports high confidence (riskcode max is 3 → "high"
                # so without this clamp the worst DAST findings never surface).
                if (
                    severity == "high"
                    and cwe_id in _CRITICAL_CWE_IDS
                    and str(alert.get("confidence", "")) in {"3", "high", "High"}
                ):
                    severity = "critical"

                instances = alert.get("instances") or [{}]
                for inst in instances:
                    uri = inst.get("uri") or site_url
                    method = inst.get("method", "")
                    file_path = f"{method} {uri}".strip()
                    message = f"{title} — {description[:200]}".strip(" —")

                    dedup = compute_dedup_hash(rule_id, file_path, title)
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
                            cvss_score=None,
                            raw_data={
                                "alert": title,
                                "uri": uri,
                                "method": method,
                                "param": inst.get("param", ""),
                                "evidence": inst.get("evidence", ""),
                                "attack": inst.get("attack", ""),
                                "solution": solution,
                                "reference": alert.get("reference", ""),
                                "confidence": alert.get("confidence", ""),
                                "wascid": alert.get("wascid", ""),
                                "dedup_hash": dedup,
                            },
                        )
                    )

        return findings

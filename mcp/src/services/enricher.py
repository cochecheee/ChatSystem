from __future__ import annotations

from cwe2.database import Database

from ..models.schemas import FindingCreate

# ---------------------------------------------------------------------------
# OWASP Top 10 2021 — CWE → category mapping (most common SAST findings)
# ---------------------------------------------------------------------------

_OWASP_2021: dict[int, str] = {
    # A01 – Broken Access Control
    22: "A01:2021 - Broken Access Control",
    23: "A01:2021 - Broken Access Control",
    284: "A01:2021 - Broken Access Control",
    285: "A01:2021 - Broken Access Control",
    352: "A01:2021 - Broken Access Control",
    601: "A01:2021 - Broken Access Control",
    639: "A01:2021 - Broken Access Control",
    862: "A01:2021 - Broken Access Control",
    863: "A01:2021 - Broken Access Control",
    # A02 – Cryptographic Failures
    310: "A02:2021 - Cryptographic Failures",
    319: "A02:2021 - Cryptographic Failures",
    326: "A02:2021 - Cryptographic Failures",
    327: "A02:2021 - Cryptographic Failures",
    328: "A02:2021 - Cryptographic Failures",
    330: "A02:2021 - Cryptographic Failures",
    338: "A02:2021 - Cryptographic Failures",
    916: "A02:2021 - Cryptographic Failures",
    # A03 – Injection
    20: "A03:2021 - Injection",
    77: "A03:2021 - Injection",
    78: "A03:2021 - Injection",
    79: "A03:2021 - Injection",
    89: "A03:2021 - Injection",
    90: "A03:2021 - Injection",
    94: "A03:2021 - Injection",
    95: "A03:2021 - Injection",
    643: "A03:2021 - Injection",
    917: "A03:2021 - Injection",
    # A04 – Insecure Design
    209: "A04:2021 - Insecure Design",
    256: "A04:2021 - Insecure Design",
    501: "A04:2021 - Insecure Design",
    522: "A04:2021 - Insecure Design",
    # A05 – Security Misconfiguration
    16: "A05:2021 - Security Misconfiguration",
    611: "A05:2021 - Security Misconfiguration",
    614: "A05:2021 - Security Misconfiguration",
    942: "A05:2021 - Security Misconfiguration",
    # A06 – Vulnerable and Outdated Components
    1104: "A06:2021 - Vulnerable and Outdated Components",
    # A07 – Identification and Authentication Failures
    259: "A07:2021 - Identification and Authentication Failures",
    287: "A07:2021 - Identification and Authentication Failures",
    295: "A07:2021 - Identification and Authentication Failures",
    306: "A07:2021 - Identification and Authentication Failures",
    307: "A07:2021 - Identification and Authentication Failures",
    521: "A07:2021 - Identification and Authentication Failures",
    613: "A07:2021 - Identification and Authentication Failures",
    798: "A07:2021 - Identification and Authentication Failures",
    # A08 – Software and Data Integrity Failures
    345: "A08:2021 - Software and Data Integrity Failures",
    426: "A08:2021 - Software and Data Integrity Failures",
    494: "A08:2021 - Software and Data Integrity Failures",
    502: "A08:2021 - Software and Data Integrity Failures",
    # A09 – Security Logging and Monitoring Failures
    117: "A09:2021 - Security Logging and Monitoring Failures",
    223: "A09:2021 - Security Logging and Monitoring Failures",
    532: "A09:2021 - Security Logging and Monitoring Failures",
    778: "A09:2021 - Security Logging and Monitoring Failures",
    # A10 – Server-Side Request Forgery
    918: "A10:2021 - Server-Side Request Forgery (SSRF)",
}

_SEVERITY_TO_CVSS: dict[str, float] = {
    "critical": 9.5,
    "high": 7.5,
    "medium": 5.0,
    "low": 2.0,
    "info": 0.0,
}

_CWE_DB = Database()


# ---------------------------------------------------------------------------
# DataEnricher
# ---------------------------------------------------------------------------

class DataEnricher:
    """Enriches a FindingCreate with CWE details, OWASP category, and CVSS score."""

    def enrich(self, finding: FindingCreate) -> FindingCreate:
        cwe_num = self._parse_cwe_number(finding.cwe_id)
        cwe_name = self._get_cwe_name(cwe_num)
        owasp = _OWASP_2021.get(cwe_num) if cwe_num else None
        cvss = self._resolve_cvss(finding.severity, finding.cvss_score)

        enriched_raw = dict(finding.raw_data or {})
        if cwe_name:
            enriched_raw["cwe_name"] = cwe_name
        if owasp:
            enriched_raw["owasp_category"] = owasp

        return FindingCreate(
            artifact_id=finding.artifact_id,
            tool=finding.tool,
            rule_id=finding.rule_id,
            severity=finding.severity,
            message=finding.message,
            file_path=finding.file_path,
            line_number=finding.line_number,
            cwe_id=finding.cwe_id,
            cvss_score=cvss,
            raw_data=enriched_raw,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _parse_cwe_number(cwe_id: str | None) -> int | None:
        if not cwe_id:
            return None
        parts = cwe_id.upper().replace("CWE-", "").strip()
        return int(parts) if parts.isdigit() else None

    @staticmethod
    def _get_cwe_name(cwe_num: int | None) -> str | None:
        if cwe_num is None:
            return None
        try:
            weakness = _CWE_DB.get(cwe_num)
            return weakness.name if weakness else None
        except Exception:
            return None

    @staticmethod
    def _resolve_cvss(severity: str, existing_score: float | None) -> float | None:
        if existing_score is not None:
            return existing_score
        return _SEVERITY_TO_CVSS.get(severity.lower())

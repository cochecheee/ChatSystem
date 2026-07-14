from __future__ import annotations

import re

from cwe2.database import Database

from ..models.schemas import FindingCreate

# ---------------------------------------------------------------------------
# OWASP Top 10 2021 taxonomy — canonical class code → label / reference URL,
# plus a CWE → class-code map (most common SAST/SCA findings). The class code
# ("A03") is the first-class category we store on Finding.owasp_class so the
# dashboard can filter/group by vulnerability class; the label is the human
# string kept in raw_data['owasp_category'].
# ---------------------------------------------------------------------------

_OWASP_LABEL: dict[str, str] = {
    "A01": "A01:2021 - Broken Access Control",
    "A02": "A02:2021 - Cryptographic Failures",
    "A03": "A03:2021 - Injection",
    "A04": "A04:2021 - Insecure Design",
    "A05": "A05:2021 - Security Misconfiguration",
    "A06": "A06:2021 - Vulnerable and Outdated Components",
    "A07": "A07:2021 - Identification and Authentication Failures",
    "A08": "A08:2021 - Software and Data Integrity Failures",
    "A09": "A09:2021 - Security Logging and Monitoring Failures",
    "A10": "A10:2021 - Server-Side Request Forgery (SSRF)",
    "A00": "A00 - Uncategorized",
}

_OWASP_URL: dict[str, str] = {
    "A01": "https://owasp.org/Top10/A01_2021-Broken_Access_Control/",
    "A02": "https://owasp.org/Top10/A02_2021-Cryptographic_Failures/",
    "A03": "https://owasp.org/Top10/A03_2021-Injection/",
    "A04": "https://owasp.org/Top10/A04_2021-Insecure_Design/",
    "A05": "https://owasp.org/Top10/A05_2021-Security_Misconfiguration/",
    "A06": "https://owasp.org/Top10/A06_2021-Vulnerable_and_Outdated_Components/",
    "A07": "https://owasp.org/Top10/A07_2021-Identification_and_Authentication_Failures/",
    "A08": "https://owasp.org/Top10/A08_2021-Software_and_Data_Integrity_Failures/",
    "A09": "https://owasp.org/Top10/A09_2021-Security_Logging_and_Monitoring_Failures/",
    "A10": "https://owasp.org/Top10/A10_2021-Server-Side_Request_Forgery_%28SSRF%29/",
}

_CWE_TO_OWASP: dict[int, str] = {
    # A01 – Broken Access Control
    22: "A01", 23: "A01", 200: "A01", 269: "A01", 284: "A01", 285: "A01",
    352: "A01", 601: "A01", 639: "A01", 732: "A01", 862: "A01", 863: "A01",
    # A02 – Cryptographic Failures
    310: "A02", 319: "A02", 326: "A02", 327: "A02", 328: "A02", 330: "A02",
    338: "A02", 916: "A02",
    # A03 – Injection
    20: "A03", 74: "A03", 77: "A03", 78: "A03", 79: "A03", 89: "A03",
    90: "A03", 94: "A03", 95: "A03", 113: "A03", 116: "A03", 643: "A03",
    917: "A03",
    # A04 – Insecure Design
    209: "A04", 256: "A04", 501: "A04", 522: "A04",
    # A05 – Security Misconfiguration
    16: "A05", 611: "A05", 614: "A05", 942: "A05",
    # A06 – Vulnerable and Outdated Components
    1104: "A06",
    # A07 – Identification and Authentication Failures
    259: "A07", 287: "A07", 295: "A07", 306: "A07", 307: "A07", 521: "A07",
    613: "A07", 798: "A07",
    # A08 – Software and Data Integrity Failures
    345: "A08", 426: "A08", 494: "A08", 502: "A08",
    # A09 – Security Logging and Monitoring Failures
    117: "A09", 223: "A09", 532: "A09", 778: "A09",
    # A10 – Server-Side Request Forgery
    918: "A10",
}

# Dependency-scan tools → their findings default to A06 when no CWE resolves.
# Broader than finding_repo.DEPS_TOOLS on purpose (safety/npm-audit findings are
# dependency vulns even though they aren't part of the sast/deps *filter* set).
_DEPS_TOOLS: set[str] = {
    "dependency-check", "owasp-dependency-check", "trivy", "trivy-deps",
    "safety", "npm-audit", "pip-audit",
}

# Ordered keyword heuristics (specific → general) for findings without a mapped
# CWE. First matching rule wins; no match → "A00" (Uncategorized).
_KEYWORD_RULES: list[tuple[tuple[str, ...], str]] = [
    (("sql injection", "sqli", "sql-injection", "sql query"), "A03"),
    (("command injection", "os command", "code injection", "code execution", "remote code execution", "eval("), "A03"),
    (("xss", "cross-site scripting", "cross site scripting", "xpath injection", "ldap injection", "template injection"), "A03"),
    (("ssrf", "server-side request", "server side request"), "A10"),
    (("xxe", "xml external entity"), "A05"),
    (("path traversal", "directory traversal", "zip slip"), "A01"),
    (("csrf", "cross-site request forgery"), "A01"),
    (("open redirect",), "A01"),
    (("idor", "access control", "authorization", "privilege escalation", "missing authz"), "A01"),
    (("hardcoded", "hard-coded", "secret", "credential", "api key", "private key"), "A07"),
    (("weak hash", "md5", "sha1", "weak cipher", "weak crypto", "insecure random", "predictable random", "ecb mode", "broken crypto", "cleartext", "plaintext password"), "A02"),
    (("insecure deserial", "deserialization", "pickle", "unmarshal", "unsafe yaml"), "A08"),
    (("log injection", "log forging", "log4j", "insufficient logging", "sensitive data in log"), "A09"),
    (("misconfiguration", "cors", "debug mode", "default configuration", "security header", "clickjacking"), "A05"),
    (("outdated", "vulnerable and outdated", "known vulnerability", "cve-"), "A06"),
]

_SEVERITY_TO_CVSS: dict[str, float] = {
    "critical": 9.5,
    "high": 7.5,
    "medium": 5.0,
    "low": 2.0,
    "info": 0.0,
}

_CWE_DB = Database()


# ---------------------------------------------------------------------------
# Module-level helpers (also used by scripts/backfill_owasp_class.py + tests)
# ---------------------------------------------------------------------------

def parse_cwe_number(cwe_id: str | None) -> int | None:
    if not cwe_id:
        return None
    parts = cwe_id.upper().replace("CWE-", "").strip()
    return int(parts) if parts.isdigit() else None


def get_cwe_name(cwe_num: int | None) -> str | None:
    if cwe_num is None:
        return None
    try:
        weakness = _CWE_DB.get(cwe_num)
        return weakness.name if weakness else None
    except Exception:
        return None


def _classify_fallback(finding: FindingCreate) -> str:
    """Category for a finding with no mapped CWE: deps tool → A06, else keyword
    heuristic on rule_id + message, else A00 (Uncategorized). Never empty."""
    tool = (finding.tool or "").lower()
    if tool in _DEPS_TOOLS:
        return "A06"
    text = f"{finding.rule_id or ''} {finding.message or ''}".lower()
    for keywords, code in _KEYWORD_RULES:
        if any(k in text for k in keywords):
            return code
    return "A00"


def classify_owasp(finding: FindingCreate) -> tuple[str, str]:
    """Return (owasp_class_code, owasp_label). CWE map first, then fallback;
    always resolves to a non-empty class code."""
    cwe_num = parse_cwe_number(finding.cwe_id)
    code = _CWE_TO_OWASP.get(cwe_num) if cwe_num else None
    if code is None:
        code = _classify_fallback(finding)
    return code, _OWASP_LABEL.get(code, _OWASP_LABEL["A00"])


def build_references(finding: FindingCreate, cwe_num: int | None, code: str | None) -> list[dict]:
    """Standard external references for a finding: CWE (MITRE), OWASP class
    (owasp.org), CVE (NVD), GHSA advisory, plus any tool-provided reference
    URLs (ZAP `reference`, npm `advisory_url`). De-duplicated by URL."""
    refs: list[dict] = []
    seen: set[str] = set()

    def add(label: str, url: str | None) -> None:
        if url and url.startswith("http") and url not in seen:
            seen.add(url)
            refs.append({"label": label, "url": url})

    if cwe_num:
        name = get_cwe_name(cwe_num)
        label = f"CWE-{cwe_num}" + (f": {name}" if name else "")
        add(label, f"https://cwe.mitre.org/data/definitions/{cwe_num}.html")
    if code and code in _OWASP_URL:
        add(_OWASP_LABEL.get(code, code), _OWASP_URL[code])

    rd = finding.raw_data or {}
    # CVE → NVD (trivy/dependency-check carry a CVE id under various keys).
    for key in ("cve", "vuln_id", "vulnerability_id", "id"):
        val = rd.get(key)
        if isinstance(val, str) and val.upper().startswith("CVE-"):
            cve = val.upper()
            add(cve, f"https://nvd.nist.gov/vuln/detail/{cve}")
    # GHSA / npm advisory URL.
    add("Advisory", rd.get("advisory_url") if isinstance(rd.get("advisory_url"), str) else None)
    # Tool-provided references (ZAP `reference` may hold several URLs).
    ref = rd.get("reference")
    if isinstance(ref, str):
        for u in re.split(r"\s+", ref.strip()):
            add("Reference", u)
    elif isinstance(ref, list):
        for u in ref:
            if isinstance(u, str):
                add("Reference", u)
    return refs


# ---------------------------------------------------------------------------
# DataEnricher
# ---------------------------------------------------------------------------

class DataEnricher:
    """Enriches a FindingCreate with CWE details, OWASP category + class,
    standard reference URLs, and CVSS score."""

    def enrich(self, finding: FindingCreate) -> FindingCreate:
        cwe_num = parse_cwe_number(finding.cwe_id)
        cwe_name = get_cwe_name(cwe_num)
        owasp_class, owasp_label = classify_owasp(finding)
        references = build_references(finding, cwe_num, owasp_class)
        had_real_cvss = finding.cvss_score is not None
        cvss = self._resolve_cvss(finding.severity, finding.cvss_score)

        enriched_raw = dict(finding.raw_data or {})
        if cwe_name:
            enriched_raw["cwe_name"] = cwe_name
        # owasp_category label kept under the existing key (report + FindingDetail
        # already read it). owasp_class is the code, mirrored into raw_data for
        # Python-side stats and onto the Finding.owasp_class column for filtering.
        enriched_raw["owasp_category"] = owasp_label
        enriched_raw["owasp_class"] = owasp_class
        if references:
            enriched_raw["references"] = references

        # V4.1 — mark whether the stored CVSS is a real tool score or one
        # derived from the severity label (so the dashboard doesn't present a
        # synthetic "7.5" as if the scanner reported it). The normalizer's
        # provenance block (raw_data["_severity"]) already carries cvss_kind
        # (v3/v2/security-severity) for real scores.
        sev_prov = dict(enriched_raw.get("_severity") or {})
        if had_real_cvss:
            sev_prov.setdefault("cvss_source", "tool")
        elif cvss is not None:
            sev_prov["cvss_source"] = "derived-from-label"
            sev_prov.setdefault("cvss", cvss)
        else:
            sev_prov.setdefault("cvss_source", "none")
        if sev_prov:
            enriched_raw["_severity"] = sev_prov

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
            owasp_class=owasp_class,
            raw_data=enriched_raw,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_cvss(severity: str, existing_score: float | None) -> float | None:
        if existing_score is not None:
            return existing_score
        return _SEVERITY_TO_CVSS.get(severity.lower())

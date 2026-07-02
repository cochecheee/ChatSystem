"""Shared severity mappings and resolution helpers for all normalizers.

Different tools express severity in different vocabularies (SARIF levels,
CVSS numeric scores, SpotBugs priorities, ESLint numeric levels, npm/Safety
labels). These tables and helpers centralise the mapping into our canonical
``critical | high | medium | low | info`` buckets so every normalizer resolves
severity the same way.
"""
from __future__ import annotations

# --- SARIF result level (§3.27.10) -----------------------------------------
_SARIF_LEVEL_TO_SEVERITY: dict[str, str] = {
    "error": "high",
    "warning": "medium",
    "note": "low",
    "none": "info",
}

# --- SpotBugs bug priority -------------------------------------------------
_SPOTBUGS_PRIORITY_TO_SEVERITY: dict[str, str] = {
    "1": "high",
    "2": "medium",
    "3": "low",
    "4": "info",
    "5": "info",
}

# --- ESLint numeric severity ----------------------------------------------
_ESLINT_SEVERITY_TO_SEVERITY: dict[int, str] = {
    2: "high",     # eslint "error"
    1: "low",      # eslint "warn" — usually style/lint, not security
    0: "info",     # eslint "off"
}

# --- Canonical/uppercase string labels ------------------------------------
_UPPERCASE_TO_SEVERITY: dict[str, str] = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    "INFO": "info",
    # Semgrep `properties.severity` variants
    "ERROR": "high",
    "WARNING": "medium",
    "INFORMATIONAL": "info",
    # CodeQL `properties["problem.severity"]` variants
    "RECOMMENDATION": "low",
    # NOTE: "UNKNOWN" deliberately NOT mapped — handled by _sca_severity()
    # which falls back to CVSS or "medium" (pending triage) rather than info.
}

# --- npm audit labels ------------------------------------------------------
# `npm audit --json` uses critical|high|moderate|low|info; map "moderate" to
# our canonical "medium". The others pass straight through _UPPERCASE_TO_SEVERITY.
_NPM_SEVERITY_TO_SEVERITY: dict[str, str] = {
    "critical": "critical",
    "high": "high",
    "moderate": "medium",
    "low": "low",
    "info": "info",
}

# CWE classes severe enough that a tool-reported "high" should be promoted to
# "critical" when seen via DAST. Mirrors OWASP Top 10 (Injection / RCE classes).
_CRITICAL_CWE_IDS: frozenset[str] = frozenset({
    "CWE-77",   # Command Injection
    "CWE-78",   # OS Command Injection
    "CWE-89",   # SQL Injection
    "CWE-94",   # Code Injection
    "CWE-95",   # eval() Injection
    "CWE-502",  # Deserialization of Untrusted Data
    "CWE-917",  # Expression Language Injection
})


def _sca_severity(sev_raw: str, cvss_score: float | None) -> str:
    """SCA tools (DepCheck/Trivy) severity resolution.

    Preference order:
      1. CVSS numeric score (when present) — most trustworthy signal
      2. String severity label
      3. Default "medium" (treat-as-pending-triage, NOT info)
    """
    s = (sev_raw or "").strip().upper()
    # When the tool says UNKNOWN or empty, lean on CVSS if available.
    if s in {"", "UNKNOWN"}:
        if cvss_score is not None and cvss_score > 0:
            return _security_severity_to_label(float(cvss_score))
        return "medium"
    mapped = _UPPERCASE_TO_SEVERITY.get(s)
    if mapped:
        return mapped
    # Fallback for unrecognised strings: CVSS if available, else medium
    if cvss_score is not None and cvss_score > 0:
        return _security_severity_to_label(float(cvss_score))
    return "medium"


def _security_severity_to_label(score: float) -> str:
    """Map CVSS-style numeric score (0–10) to severity bucket.

    Mirrors GitHub Advanced Security thresholds:
    https://docs.github.com/en/code-security/code-scanning/managing-code-scanning-alerts/about-code-scanning-alerts#about-alert-severity-and-security-severity-levels
    """
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    if score > 0:
        return "low"
    return "info"

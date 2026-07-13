"""Shared severity mappings and resolution helpers for all normalizers.

Different tools express severity in different vocabularies (SARIF levels,
CVSS numeric scores, SpotBugs priorities, ESLint numeric levels, npm/Safety
labels). These tables and helpers centralise the mapping into our canonical
``critical | high | medium | low | info`` buckets so every normalizer resolves
severity the same way.

V4.1 — `resolve_severity()` is the single entry point every normalizer uses to
combine a text label and/or a numeric score into one canonical bucket. Policy:
take the **more severe** of the label-band and the score-band (never under-rate),
correct CVSS v2 vs v3 banding, and return provenance (original label, both bands,
which signal decided, whether they disagreed) so the dashboard can explain "why".
"""
from __future__ import annotations

from dataclasses import dataclass

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


# --- Canonical order + superset text-label table ---------------------------
CANON_ORDER: tuple[str, ...] = ("info", "low", "medium", "high", "critical")
CANON_RANK: dict[str, int] = {s: i for i, s in enumerate(CANON_ORDER)}

# One superset table mapping ANY text label a tool might emit → canonical band.
# Combines the canonical/Semgrep/CodeQL/npm words above with SARIF level words
# and SonarQube severities. Unknown / "UNKNOWN" → not present (None) so the
# resolver can fall back to the score or the "medium" pending-triage default.
# NOTE: SonarQube findings aren't ingested today; the crosswalk is defensive.
# "CRITICAL" stays → critical (real tools use it that way); only the
# unambiguous Sonar words are added. See docs/severity-normalization.md.
_LABEL_BAND: dict[str, str] = {
    **_UPPERCASE_TO_SEVERITY,      # CRITICAL/HIGH/MEDIUM/LOW/INFO + ERROR/WARNING/INFORMATIONAL/RECOMMENDATION
    "MODERATE": "medium",          # npm / generic synonym
    "NOTE": "low",                 # SARIF level word
    "NONE": "info",                # SARIF level word
    "BLOCKER": "critical",         # SonarQube
    "MAJOR": "medium",             # SonarQube
    "MINOR": "low",                # SonarQube
}


def band_from_label(raw: str | None) -> str | None:
    """Map a text severity label to a canonical band, or None if unrecognised."""
    if not raw:
        return None
    return _LABEL_BAND.get(raw.strip().upper())


def band_from_score(score: float | None, kind: str | None = "v3") -> str | None:
    """Map a numeric score to a canonical band, or None when absent (<= 0).

    CVSS v3 / GitHub `security-severity` use the GitHub thresholds (a real
    "critical" band ≥ 9.0). **CVSS v2 has no critical band** — its max band is
    High (7.0–10) — so applying v3 cutoffs to a v2 score wrongly invents
    criticals. `kind="v2"` uses the v2 bands instead.
    """
    if score is None:
        return None
    try:
        s = float(score)
    except (TypeError, ValueError):
        return None
    if s <= 0:
        return None
    if (kind or "").lower() == "v2":
        if s >= 7.0:
            return "high"
        if s >= 4.0:
            return "medium"
        return "low"
    # v3 / security-severity / default
    if s >= 9.0:
        return "critical"
    if s >= 7.0:
        return "high"
    if s >= 4.0:
        return "medium"
    return "low"


@dataclass
class SeverityResult:
    severity: str                    # canonical bucket
    cvss_score: float | None = None
    cvss_kind: str | None = None     # "v3" | "v2" | "security-severity" | None
    original_label: str | None = None
    band_label: str | None = None    # band derived from the label (or None)
    band_score: str | None = None    # band derived from the score (or None)
    source: str = "default"          # "max(label,score)"|"label"|"score"|"default"
    disagreement: bool = False       # label-band and score-band differ

    def provenance(self) -> dict:
        """Serializable block stored under a finding's raw_data['_severity']."""
        return {
            "original_label": self.original_label,
            "cvss": self.cvss_score,
            "cvss_kind": self.cvss_kind,
            "band_label": self.band_label,
            "band_score": self.band_score,
            "normalized": self.severity,
            "source": self.source,
            "disagreement": self.disagreement,
        }


def resolve_severity(
    *,
    raw_label: str | None = None,
    label_band: str | None = None,
    score: float | None = None,
    score_kind: str | None = None,
) -> SeverityResult:
    """Combine a text label and/or a numeric score into one canonical severity.

    Policy = MORE SEVERE: `max(band_from_label, band_from_score)` so a finding is
    never under-rated when its two signals disagree. When neither signal
    resolves, default to "medium" (pending triage), never a silent "info".

    - `raw_label`: a text label (e.g. Trivy "HIGH", Semgrep "ERROR"); mapped via
      `band_from_label`. Also kept verbatim as `original_label` for provenance.
    - `label_band`: pre-computed band for private numeric scales (SpotBugs
      priority, ESLint level) whose values don't map through the text table.
    - `score` + `score_kind`: numeric CVSS ("v3"/"v2") or GitHub
      "security-severity".
    """
    bl = label_band or band_from_label(raw_label)
    bs = band_from_score(score, score_kind)
    present = [b for b in (bl, bs) if b]
    if present:
        severity = max(present, key=CANON_RANK.__getitem__)
        source = "max(label,score)" if (bl and bs) else ("label" if bl else "score")
    else:
        severity = "medium"
        source = "default"
    return SeverityResult(
        severity=severity,
        cvss_score=float(score) if score not in (None, 0, 0.0) else None,
        cvss_kind=score_kind if bs else None,
        original_label=raw_label,
        band_label=bl,
        band_score=bs,
        source=source,
        disagreement=bool(bl and bs and bl != bs),
    )


def _sca_severity(sev_raw: str, cvss_score: float | None) -> str:
    """Backward-compatible SCA severity helper — now a thin wrapper over
    `resolve_severity` (more-severe of label vs CVSS). CVSS version is unknown
    at this call site, so scores are banded with the v3 thresholds."""
    return resolve_severity(
        raw_label=sev_raw or None, score=cvss_score, score_kind="v3",
    ).severity


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

"""V4.1 — unified severity resolution (numeric CVSS <-> text labels).

Verifies the more-severe policy (max of label-band and score-band), correct
CVSS v2 vs v3 banding, the extended label vocabulary (SonarQube / generic
synonyms), the "medium pending-triage" default, and that normalizers emit the
`raw_data['_severity']` provenance block (original label, both bands, source,
disagreement)."""
import json

from src.core.db import AsyncSessionLocal
from src.models.entities import Artifact, Finding, Project
from src.services.normalizers.severity import (
    band_from_label,
    band_from_score,
    resolve_severity,
)


def _sev_finding(aid, pid, tool, sev, prov, file="f.py"):
    return Finding(
        artifact_id=aid, project_id=pid, tool=tool, rule_id=f"{tool}.r",
        severity=sev, message="m", file_path=file, status="pending_review",
        raw_data=({"_severity": prov} if prov else {}),
    )


# --- band_from_score: CVSS v2 vs v3 ---------------------------------------

def test_v3_bands():
    assert band_from_score(9.2, "v3") == "critical"
    assert band_from_score(7.5, "v3") == "high"
    assert band_from_score(4.0, "v3") == "medium"
    assert band_from_score(1.0, "v3") == "low"
    assert band_from_score(0, "v3") is None
    assert band_from_score(None, "v3") is None


def test_v2_has_no_critical_band():
    # CVSS v2 max band is High — 9.5 must NOT become "critical".
    assert band_from_score(9.5, "v2") == "high"
    assert band_from_score(7.0, "v2") == "high"
    assert band_from_score(4.0, "v2") == "medium"
    assert band_from_score(3.9, "v2") == "low"


# --- band_from_label: extended vocabulary ----------------------------------

def test_label_vocab():
    assert band_from_label("CRITICAL") == "critical"
    assert band_from_label("high") == "high"
    assert band_from_label("moderate") == "medium"   # npm / generic
    assert band_from_label("ERROR") == "high"         # Semgrep
    assert band_from_label("recommendation") == "low" # CodeQL
    assert band_from_label("note") == "low"           # SARIF level word
    assert band_from_label("none") == "info"
    # SonarQube
    assert band_from_label("BLOCKER") == "critical"
    assert band_from_label("MAJOR") == "medium"
    assert band_from_label("MINOR") == "low"
    # unknown / empty -> None (resolver falls back to score or medium)
    assert band_from_label("banana") is None
    assert band_from_label("UNKNOWN") is None
    assert band_from_label("") is None
    assert band_from_label(None) is None


# --- resolve_severity: more-severe policy ----------------------------------

def test_more_severe_label_vs_score():
    # Trivy label HIGH but CVSS 9.5 (v3) -> promote to critical.
    r = resolve_severity(raw_label="HIGH", score=9.5, score_kind="v3")
    assert r.severity == "critical"
    assert r.band_label == "high" and r.band_score == "critical"
    assert r.disagreement is True
    assert r.source == "max(label,score)"
    assert r.cvss_score == 9.5 and r.cvss_kind == "v3"


def test_v2_score_with_label_does_not_overpromote():
    # label CRITICAL + v2 9.5 (band high) -> max = critical (label wins), no invented critical from v2.
    r = resolve_severity(raw_label="CRITICAL", score=9.5, score_kind="v2")
    assert r.severity == "critical"
    assert r.band_score == "high"           # v2 banding, not critical
    # v2 score alone (no label) stays high
    r2 = resolve_severity(score=9.5, score_kind="v2")
    assert r2.severity == "high"


def test_agreement_no_disagreement_flag():
    r = resolve_severity(raw_label="critical", score=9.5, score_kind="v3")
    assert r.severity == "critical" and r.disagreement is False


def test_default_is_medium_not_info():
    r = resolve_severity(raw_label="banana")          # unknown, no score
    assert r.severity == "medium" and r.source == "default"
    assert r.band_label is None and r.band_score is None


def test_label_band_passthrough_for_numeric_scales():
    # SpotBugs/ESLint pass a precomputed band + a descriptive original_label.
    r = resolve_severity(label_band="high", raw_label="priority=1")
    assert r.severity == "high" and r.original_label == "priority=1"
    assert r.source == "label"


def test_provenance_shape():
    p = resolve_severity(raw_label="HIGH", score=9.8, score_kind="v3").provenance()
    assert set(p) >= {"original_label", "cvss", "cvss_kind", "band_label",
                      "band_score", "normalized", "source", "disagreement"}
    assert p["normalized"] == "critical" and p["disagreement"] is True


# --- normalizer-level integration ------------------------------------------

def test_trivy_promotes_and_records_provenance():
    from src.services.normalizers import TrivyJsonNormalizer
    content = json.dumps({"Results": [{"Target": "os", "Vulnerabilities": [
        {"VulnerabilityID": "CVE-9", "Severity": "HIGH", "Title": "t",
         "CVSS": {"nvd": {"V3Score": 9.5}}},
    ]}]})
    f = TrivyJsonNormalizer().normalize(content, artifact_id=1)[0]
    assert f.severity == "critical"                      # promoted (label HIGH + CVSS 9.5)
    prov = f.raw_data["_severity"]
    assert prov["original_label"] == "HIGH"
    assert prov["band_label"] == "high" and prov["band_score"] == "critical"
    assert prov["disagreement"] is True and prov["cvss_kind"] == "v3"
    assert f.cvss_score == 9.5


def test_trivy_v2_not_overpromoted():
    from src.services.normalizers import TrivyJsonNormalizer
    content = json.dumps({"Results": [{"Target": "os", "Vulnerabilities": [
        {"VulnerabilityID": "CVE-2", "Severity": "MEDIUM", "Title": "t",
         "CVSS": {"nvd": {"V2Score": 9.5}}},
    ]}]})
    f = TrivyJsonNormalizer().normalize(content, artifact_id=1)[0]
    # v2 9.5 band = high; label MEDIUM -> max = high; NOT critical.
    assert f.severity == "high"
    assert f.raw_data["_severity"]["cvss_kind"] == "v2"


def test_zap_promotion_records_source():
    from src.services.normalizers import ZapJsonNormalizer
    content = json.dumps({"site": [{"@name": "http://x", "alerts": [
        {"pluginid": "40018", "alert": "SQLi", "riskcode": "3", "confidence": "3",
         "cweid": "89", "desc": "d", "instances": [{"uri": "http://x/q", "method": "GET"}]},
    ]}]})
    f = ZapJsonNormalizer().normalize(content, artifact_id=1)[0]
    assert f.severity == "critical"                      # high + CWE-89 + high confidence
    assert f.raw_data["_severity"]["source"] == "promoted-dast"


# --- /findings/severity-stats endpoint -------------------------------------

async def test_severity_stats_endpoint(client):
    async with AsyncSessionLocal() as s:
        p = Project(name="SP", github_url="https://github.com/x/sp")
        s.add(p)
        await s.commit()
        await s.refresh(p)
        a = Artifact(github_artifact_id="1", project_id=p.id,
                     github_run_id=700, status="processed")
        s.add(a)
        await s.commit()
        await s.refresh(a)
        s.add_all([
            # promoted: label high, score critical -> critical (real CVSS)
            _sev_finding(a.id, p.id, "trivy", "critical", {
                "original_label": "HIGH", "cvss": 9.5, "cvss_kind": "v3",
                "band_label": "high", "band_score": "critical", "normalized": "critical",
                "source": "max(label,score)", "disagreement": True, "cvss_source": "tool"}, "a.py"),
            # disagreement but NOT promoted: label critical, score high (v2) -> critical
            _sev_finding(a.id, p.id, "dependency-check", "critical", {
                "original_label": "CRITICAL", "cvss": 9.5, "cvss_kind": "v2",
                "band_label": "critical", "band_score": "high", "normalized": "critical",
                "source": "max(label,score)", "disagreement": True, "cvss_source": "tool"}, "b.py"),
            # derived CVSS, no promotion, no disagreement
            _sev_finding(a.id, p.id, "semgrep", "medium", {
                "original_label": "WARNING", "cvss": 5.0, "cvss_kind": None,
                "band_label": "medium", "band_score": None, "normalized": "medium",
                "source": "label", "disagreement": False, "cvss_source": "derived-from-label"}, "c.py"),
            # pre-V4.1 finding: no provenance
            _sev_finding(a.id, p.id, "bandit", "low", None, "d.py"),
        ])
        await s.commit()
        pid = p.id

    r = await client.get("/findings/severity-stats", params={"project_id": pid, "run_id": 700})
    assert r.status_code == 200
    d = r.json()
    assert d["total"] == 4
    assert d["with_provenance"] == 3
    assert d["promoted"] == 1                 # only the label-high/score-critical row
    assert d["disagreements"] == 2
    assert d["cvss_real"] == 2 and d["cvss_derived"] == 1
    assert len(d["top_promoted"]) == 1
    assert d["top_promoted"][0]["normalized"] == "critical"
    assert d["top_promoted"][0]["tool"] == "trivy"
    assert d["by_tool"]["trivy"]["promoted"] == 1

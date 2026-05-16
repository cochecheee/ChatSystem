import json
import pytest

from src.services.normalizer import (
    DepCheckNormalizer,
    ESLintNormalizer,
    NormalizerFactory,
    SarifNormalizer,
    SpotBugsXMLNormalizer,
    TrivyJsonNormalizer,
)

# ---------------------------------------------------------------------------
# Fixtures — sample raw content
# ---------------------------------------------------------------------------

SARIF_SEMGREP = json.dumps({
    "version": "2.1.0",
    "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
    "runs": [{
        "tool": {"driver": {"name": "Semgrep", "version": "1.0"}},
        "results": [
            {
                "ruleId": "python.lang.security.audit.exec-use",
                "level": "error",
                "message": {"text": "Use of exec() is dangerous"},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": "src/app.py"},
                        "region": {"startLine": 42}
                    }
                }]
            },
            {
                "ruleId": "python.lang.security.audit.eval-use",
                "level": "warning",
                "message": {"text": "Use of eval() is risky"},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": "src/utils.py"},
                        "region": {"startLine": 10}
                    }
                }]
            },
        ]
    }]
})

SARIF_NO_LOCATIONS = json.dumps({
    "version": "2.1.0",
    "runs": [{
        "tool": {"driver": {"name": "CodeQL"}},
        "results": [{
            "ruleId": "java/sql-injection",
            "level": "error",
            "message": {"text": "SQL injection"},
            "locations": []
        }]
    }]
})

SPOTBUGS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<BugCollection version="4.8.6" threshold="Low" effort="Default">
  <BugInstance type="SQL_INJECTION_JDBC" priority="1" rank="1" category="SECURITY" cweid="89">
    <ShortMessage>SQL injection via JDBC</ShortMessage>
    <LongMessage>Nonconstant string passed to execute method on an SQL statement</LongMessage>
    <SourceLine classname="com.example.Service" start="42" end="45" sourcepath="Service.java"/>
  </BugInstance>
  <BugInstance type="WEAK_MESSAGE_DIGEST_MD5" priority="2" rank="5" category="SECURITY" cweid="327">
    <ShortMessage>Use of MD5 is weak</ShortMessage>
    <SourceLine classname="com.example.Crypto" start="10" sourcepath="Crypto.java"/>
  </BugInstance>
</BugCollection>"""

SPOTBUGS_XML_NO_SOURCE = """<?xml version="1.0" encoding="UTF-8"?>
<BugCollection version="4.8.6">
  <BugInstance type="NULL_DEREFERENCE" priority="3" rank="10" category="CORRECTNESS">
    <ShortMessage>Null dereference</ShortMessage>
  </BugInstance>
</BugCollection>"""

ESLINT_JSON = json.dumps([
    {
        "filePath": "/app/src/index.js",
        "messages": [
            {"ruleId": "no-eval", "severity": 2, "message": "eval can be harmful", "line": 15, "column": 5},
            {"ruleId": "no-console", "severity": 1, "message": "Unexpected console statement", "line": 20},
        ]
    },
    {
        "filePath": "/app/src/utils.js",
        "messages": []
    }
])


# ---------------------------------------------------------------------------
# SarifNormalizer
# ---------------------------------------------------------------------------

def test_sarif_parses_tool_name():
    findings = SarifNormalizer().normalize(SARIF_SEMGREP, artifact_id=1)
    assert all(f.tool == "semgrep" for f in findings)


def test_sarif_parses_two_findings():
    findings = SarifNormalizer().normalize(SARIF_SEMGREP, artifact_id=1)
    assert len(findings) == 2


def test_sarif_severity_mapping():
    findings = SarifNormalizer().normalize(SARIF_SEMGREP, artifact_id=1)
    assert findings[0].severity == "high"   # level=error
    assert findings[1].severity == "medium" # level=warning


def test_sarif_extracts_file_and_line():
    findings = SarifNormalizer().normalize(SARIF_SEMGREP, artifact_id=1)
    assert findings[0].file_path == "src/app.py"
    assert findings[0].line_number == 42


def test_sarif_missing_locations_defaults_to_unknown():
    findings = SarifNormalizer().normalize(SARIF_NO_LOCATIONS, artifact_id=1)
    assert findings[0].file_path == "unknown"
    assert findings[0].line_number is None


def test_sarif_artifact_id_propagated():
    findings = SarifNormalizer().normalize(SARIF_SEMGREP, artifact_id=99)
    assert all(f.artifact_id == 99 for f in findings)


# ---------------------------------------------------------------------------
# SpotBugsXMLNormalizer
# ---------------------------------------------------------------------------

def test_spotbugs_parses_two_findings():
    findings = SpotBugsXMLNormalizer().normalize(SPOTBUGS_XML, artifact_id=2)
    assert len(findings) == 2


def test_spotbugs_severity_mapping():
    findings = SpotBugsXMLNormalizer().normalize(SPOTBUGS_XML, artifact_id=2)
    assert findings[0].severity == "high"   # priority=1
    assert findings[1].severity == "medium" # priority=2


def test_spotbugs_extracts_cwe():
    findings = SpotBugsXMLNormalizer().normalize(SPOTBUGS_XML, artifact_id=2)
    assert findings[0].cwe_id == "CWE-89"
    assert findings[1].cwe_id == "CWE-327"


def test_spotbugs_extracts_source_line():
    findings = SpotBugsXMLNormalizer().normalize(SPOTBUGS_XML, artifact_id=2)
    assert findings[0].file_path == "Service.java"
    assert findings[0].line_number == 42


def test_spotbugs_uses_long_message():
    findings = SpotBugsXMLNormalizer().normalize(SPOTBUGS_XML, artifact_id=2)
    assert "Nonconstant string" in findings[0].message


def test_spotbugs_no_source_line_defaults():
    findings = SpotBugsXMLNormalizer().normalize(SPOTBUGS_XML_NO_SOURCE, artifact_id=2)
    assert findings[0].file_path == "unknown"
    assert findings[0].line_number is None


# ---------------------------------------------------------------------------
# ESLintNormalizer
# ---------------------------------------------------------------------------

def test_eslint_parses_two_findings():
    findings = ESLintNormalizer().normalize(ESLINT_JSON, artifact_id=3)
    assert len(findings) == 2  # empty messages array skipped


def test_eslint_severity_mapping():
    findings = ESLintNormalizer().normalize(ESLINT_JSON, artifact_id=3)
    assert findings[0].severity == "high"   # severity=2
    assert findings[1].severity == "medium" # severity=1


def test_eslint_extracts_file_and_line():
    findings = ESLintNormalizer().normalize(ESLINT_JSON, artifact_id=3)
    assert findings[0].file_path == "/app/src/index.js"
    assert findings[0].line_number == 15


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def test_deduplication_removes_duplicate():
    normalizer = SarifNormalizer()
    findings = normalizer.normalize(SARIF_SEMGREP, artifact_id=1)
    first_hash = findings[0].raw_data["dedup_hash"]

    deduped = normalizer.deduplicate(findings, existing_hashes={first_hash})
    assert len(deduped) == 1
    assert deduped[0].rule_id == findings[1].rule_id


def test_deduplication_no_existing_hashes():
    normalizer = SarifNormalizer()
    findings = normalizer.normalize(SARIF_SEMGREP, artifact_id=1)
    deduped = normalizer.deduplicate(findings, existing_hashes=set())
    assert len(deduped) == 2


def test_deduplication_removes_within_batch():
    # Same finding duplicated twice
    sarif = json.dumps({
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "Semgrep"}}, "results": [
            {"ruleId": "rule-1", "level": "error", "message": {"text": "msg"},
             "locations": [{"physicalLocation": {"artifactLocation": {"uri": "f.py"}, "region": {"startLine": 1}}}]},
            {"ruleId": "rule-1", "level": "error", "message": {"text": "msg"},
             "locations": [{"physicalLocation": {"artifactLocation": {"uri": "f.py"}, "region": {"startLine": 1}}}]},
        ]}]
    })
    normalizer = SarifNormalizer()
    findings = normalizer.normalize(sarif, artifact_id=1)
    deduped = normalizer.deduplicate(findings, existing_hashes=set())
    assert len(deduped) == 1


DEP_CHECK_JSON = json.dumps({
    "reportSchema": "1.1",
    "dependencies": [
        {
            "fileName": "spring-web-6.1.0.jar",
            "filePath": "/home/runner/spring-web-6.1.0.jar",
            "vulnerabilities": [
                {
                    "name": "CVE-2024-22259",
                    "severity": "HIGH",
                    "cwes": ["CWE-601"],
                    "description": "Redirect vulnerability in Spring Web",
                    "cvssv3": {"baseScore": 7.5},
                    "source": "NVD",
                }
            ]
        },
        {
            "fileName": "log4j-core-2.14.0.jar",
            "vulnerabilities": []
        }
    ]
})

TRIVY_JSON = json.dumps({
    "SchemaVersion": 2,
    "ArtifactName": "myapp:latest",
    "Results": [
        {
            "Target": "myapp:latest (alpine 3.15)",
            "Vulnerabilities": [
                {
                    "VulnerabilityID": "CVE-2021-44228",
                    "PkgName": "log4j-core",
                    "InstalledVersion": "2.14.1",
                    "FixedVersion": "2.15.0",
                    "Severity": "CRITICAL",
                    "Title": "Log4Shell RCE",
                    "CweIDs": ["CWE-917"],
                    "CVSS": {"nvd": {"V3Score": 10.0}},
                }
            ]
        },
        {
            "Target": "Java",
            "Vulnerabilities": None
        }
    ]
})

METADATA_JSON = json.dumps({
    "run_id": 12345,
    "status": "success",
    "timestamp": "2026-04-26T10:00:00Z",
})


# ---------------------------------------------------------------------------
# DepCheckNormalizer
# ---------------------------------------------------------------------------

def test_depcheck_parses_one_finding():
    findings = DepCheckNormalizer().normalize(DEP_CHECK_JSON, artifact_id=10)
    assert len(findings) == 1


def test_depcheck_tool_name():
    findings = DepCheckNormalizer().normalize(DEP_CHECK_JSON, artifact_id=10)
    assert findings[0].tool == "dependency-check"


def test_depcheck_severity_mapping():
    findings = DepCheckNormalizer().normalize(DEP_CHECK_JSON, artifact_id=10)
    assert findings[0].severity == "high"


def test_depcheck_extracts_cve_and_cwe():
    findings = DepCheckNormalizer().normalize(DEP_CHECK_JSON, artifact_id=10)
    assert findings[0].rule_id == "CVE-2024-22259"
    assert findings[0].cwe_id == "CWE-601"


def test_depcheck_extracts_cvss():
    findings = DepCheckNormalizer().normalize(DEP_CHECK_JSON, artifact_id=10)
    assert findings[0].cvss_score == 7.5


def test_depcheck_uses_filename_as_filepath():
    findings = DepCheckNormalizer().normalize(DEP_CHECK_JSON, artifact_id=10)
    assert "spring-web" in findings[0].file_path


def test_depcheck_empty_vulnerabilities_skipped():
    findings = DepCheckNormalizer().normalize(DEP_CHECK_JSON, artifact_id=10)
    assert all("log4j-core-2.14.0" not in f.file_path for f in findings)


# ---------------------------------------------------------------------------
# TrivyJsonNormalizer
# ---------------------------------------------------------------------------

def test_trivy_parses_one_finding():
    findings = TrivyJsonNormalizer().normalize(TRIVY_JSON, artifact_id=20)
    assert len(findings) == 1


def test_trivy_tool_name():
    findings = TrivyJsonNormalizer().normalize(TRIVY_JSON, artifact_id=20)
    assert findings[0].tool == "trivy"


def test_trivy_severity_critical():
    findings = TrivyJsonNormalizer().normalize(TRIVY_JSON, artifact_id=20)
    assert findings[0].severity == "critical"


def test_trivy_extracts_cve_and_cwe():
    findings = TrivyJsonNormalizer().normalize(TRIVY_JSON, artifact_id=20)
    assert findings[0].rule_id == "CVE-2021-44228"
    assert findings[0].cwe_id == "CWE-917"


def test_trivy_extracts_cvss():
    findings = TrivyJsonNormalizer().normalize(TRIVY_JSON, artifact_id=20)
    assert findings[0].cvss_score == 10.0


def test_trivy_none_vulnerabilities_skipped():
    # "Java" target has Vulnerabilities: None — should not crash
    findings = TrivyJsonNormalizer().normalize(TRIVY_JSON, artifact_id=20)
    assert len(findings) == 1


# ---------------------------------------------------------------------------
# NormalizerFactory
# ---------------------------------------------------------------------------

def test_factory_returns_sarif_normalizer():
    assert isinstance(NormalizerFactory.get("results.sarif"), SarifNormalizer)


def test_factory_returns_spotbugs_normalizer():
    assert isinstance(NormalizerFactory.get("spotbugs.xml"), SpotBugsXMLNormalizer)


def test_factory_returns_eslint_normalizer():
    # Without content → backward-compat fallback to ESLintNormalizer
    assert isinstance(NormalizerFactory.get("eslint-report.json"), ESLintNormalizer)


def test_factory_raises_on_unknown_extension():
    with pytest.raises(ValueError, match="No normalizer"):
        NormalizerFactory.get("report.csv")


def test_factory_detects_depcheck_json():
    assert isinstance(NormalizerFactory.get("dep-check.json", DEP_CHECK_JSON), DepCheckNormalizer)


def test_factory_detects_trivy_json():
    assert isinstance(NormalizerFactory.get("trivy-image.json", TRIVY_JSON), TrivyJsonNormalizer)


def test_factory_detects_sarif_in_json():
    assert isinstance(NormalizerFactory.get("results.json", SARIF_SEMGREP), SarifNormalizer)


def test_factory_detects_eslint_array_json():
    assert isinstance(NormalizerFactory.get("eslint.json", ESLINT_JSON), ESLintNormalizer)


def test_factory_skips_unknown_metadata_json():
    with pytest.raises(ValueError, match="Unrecognized"):
        NormalizerFactory.get("metadata.json", METADATA_JSON)


# ---------------------------------------------------------------------------
# SarifNormalizer — relatedLocations fallback (Task 1, DATA-01)
# ---------------------------------------------------------------------------

# ── CodeQL multi-location fixture ──────────────────────────────────────────
SARIF_CODEQL_RELATED_LOCATIONS = json.dumps({
    "version": "2.1.0",
    "runs": [{
        "tool": {"driver": {"name": "CodeQL"}},
        "results": [{
            "ruleId": "java/path-injection",
            "level": "error",
            "message": {"text": "Path injection via user input"},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": ""},
                    "region": {"startLine": 1}
                }
            }],
            "relatedLocations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": "src/FileController.java"},
                    "region": {"startLine": 87}
                }
            }]
        }]
    }]
})

def test_sarif_codeql_related_locations():
    findings = SarifNormalizer().normalize(SARIF_CODEQL_RELATED_LOCATIONS, artifact_id=1)
    assert len(findings) == 1
    assert findings[0].file_path == "src/FileController.java"
    assert findings[0].line_number == 87


# ── ESLint SARIF variant fixture ───────────────────────────────────────────
SARIF_ESLINT_VARIANT = json.dumps({
    "version": "2.1.0",
    "runs": [{
        "tool": {"driver": {"name": "ESLint"}},
        "results": [{
            "ruleId": "no-eval",
            "level": "error",
            "message": {"text": "eval() is dangerous"},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": "src/utils.js"},
                    "region": {"startLine": 34}
                }
            }]
        }]
    }]
})

def test_sarif_eslint_variant():
    findings = SarifNormalizer().normalize(SARIF_ESLINT_VARIANT, artifact_id=1)
    assert len(findings) == 1
    assert findings[0].tool == "eslint"
    assert findings[0].file_path == "src/utils.js"
    assert findings[0].line_number == 34


# ── Semgrep relatedLocations fallback fixture ──────────────────────────────
SARIF_SEMGREP_RELATED_LOC = json.dumps({
    "version": "2.1.0",
    "runs": [{
        "tool": {"driver": {"name": "Semgrep"}},
        "results": [{
            "ruleId": "python.lang.security.audit.exec-injection",
            "level": "error",
            "message": {"text": "exec injection"},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": ""},
                    "region": {"startLine": 1}
                }
            }],
            "relatedLocations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": "src/app.py"},
                    "region": {"startLine": 12}
                }
            }]
        }]
    }]
})

# ---------------------------------------------------------------------------
# SarifNormalizer — severity from rule properties (CodeQL/Semgrep accuracy)
# ---------------------------------------------------------------------------

def _sarif_with_rule_props(rule_id: str, level: str, props: dict) -> str:
    return json.dumps({
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "CodeQL",
                "rules": [{"id": rule_id, "properties": props}],
            }},
            "results": [{
                "ruleId": rule_id,
                "level": level,
                "message": {"text": "msg"},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": "f.java"},
                    "region": {"startLine": 1},
                }}],
            }],
        }],
    })


def test_sarif_severity_uses_security_severity_critical():
    sarif = _sarif_with_rule_props("java/sqli", "error", {"security-severity": "9.8"})
    findings = SarifNormalizer().normalize(sarif, artifact_id=1)
    assert findings[0].severity == "critical"


def test_sarif_severity_uses_security_severity_medium():
    # CVSS 5.0 → medium, even though SARIF level says "error" (which would map to "high")
    sarif = _sarif_with_rule_props("java/info-leak", "error", {"security-severity": "5.0"})
    findings = SarifNormalizer().normalize(sarif, artifact_id=1)
    assert findings[0].severity == "medium"


def test_sarif_severity_uses_problem_severity_recommendation():
    sarif = _sarif_with_rule_props("java/style", "warning", {"problem.severity": "recommendation"})
    findings = SarifNormalizer().normalize(sarif, artifact_id=1)
    assert findings[0].severity == "low"


def test_sarif_severity_uses_semgrep_properties_severity():
    sarif = _sarif_with_rule_props("py/eval", "warning", {"severity": "ERROR"})
    findings = SarifNormalizer().normalize(sarif, artifact_id=1)
    assert findings[0].severity == "high"


def test_sarif_severity_falls_back_to_level_when_no_props():
    # No properties → uses SARIF level
    sarif = _sarif_with_rule_props("py/x", "note", {})
    findings = SarifNormalizer().normalize(sarif, artifact_id=1)
    assert findings[0].severity == "low"


def test_sarif_severity_invalid_security_severity_falls_through():
    sarif = _sarif_with_rule_props("py/x", "error", {"security-severity": "not-a-number"})
    findings = SarifNormalizer().normalize(sarif, artifact_id=1)
    # Falls back to level=error → high
    assert findings[0].severity == "high"


def test_sarif_semgrep_related_locations():
    findings = SarifNormalizer().normalize(SARIF_SEMGREP_RELATED_LOC, artifact_id=1)
    assert len(findings) == 1
    assert findings[0].file_path == "src/app.py"
    assert findings[0].line_number == 12


# ---------------------------------------------------------------------------
# DepCheckNormalizer — version fields (Task 2, DATA-01)
# ---------------------------------------------------------------------------

# ── DepCheck version fields ────────────────────────────────────────────────
DEP_CHECK_JSON_WITH_PURL = json.dumps({
    "dependencies": [{
        "fileName": "log4j-1.2.17.jar",
        "filePath": "/app/libs/log4j-1.2.17.jar",
        "packages": [{"id": "pkg:maven/log4j/log4j@1.2.17"}],
        "vulnerabilities": [{
            "name": "CVE-2019-17571",
            "severity": "CRITICAL",
            "description": "Deserialization vulnerability in log4j",
            "source": "NVD",
        }]
    }]
})

def test_depcheck_stores_pkg_version_fields():
    findings = DepCheckNormalizer().normalize(DEP_CHECK_JSON_WITH_PURL, artifact_id=4)
    assert len(findings) >= 1
    f = findings[0]
    assert f.raw_data["pkg_name"] != ""
    assert f.raw_data["installed_version"] == "1.2.17"
    assert "fixed_version" in f.raw_data


DEP_CHECK_JSON_NO_PURL = json.dumps({
    "dependencies": [{
        "fileName": "commons-codec.jar",
        "filePath": "/app/libs/commons-codec.jar",
        "vulnerabilities": [{
            "name": "CVE-2020-XXXX",
            "severity": "HIGH",
            "description": "Example vulnerability",
            "source": "NVD",
        }]
    }]
})

def test_depcheck_missing_purl_graceful():
    findings = DepCheckNormalizer().normalize(DEP_CHECK_JSON_NO_PURL, artifact_id=4)
    assert len(findings) >= 1
    assert findings[0].raw_data.get("installed_version") is None
    assert "fixed_version" in findings[0].raw_data

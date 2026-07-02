"""V3.8 — SARIF severity resolution regression tests.

Reproduces three production bugs that collapsed real high/critical findings
to `info`, using SARIF shapes verified against live CodeQL/Semgrep output:

  1. CodeQL stores rules in `tool.extensions[].rules` (driver.rules empty) —
     they must still be indexed so security-severity/problem.severity/CWE
     resolve.
  2. Semgrep/Bandit omit `result.level`; severity lives in the rule's
     `defaultConfiguration.level` and must be inherited.
  3. An unresolved level must default to `medium`, never `info`.
Plus CWE parsing for Semgrep's "CWE-89: ..." tag format.
"""
from src.services.normalizers import SarifNormalizer


def _norm(sarif: dict) -> list:
    import json
    return SarifNormalizer().normalize(json.dumps(sarif), artifact_id=1)


# --- Bug 1: CodeQL rules in tool.extensions -------------------------------

def test_codeql_extensions_rules_resolve_severity_and_cwe():
    """CodeQL: driver.rules empty, rule metadata in extensions. Result has no
    level. Must read security-severity (7.8 -> high) and CWE-079 from the
    extension rule."""
    sarif = {
        "runs": [{
            "tool": {
                "driver": {"name": "CodeQL", "rules": []},
                "extensions": [{
                    "name": "codeql/python-queries",
                    "rules": [{
                        "id": "py/reflective-xss",
                        "properties": {
                            "security-severity": "7.8",
                            "problem.severity": "error",
                            "tags": ["security", "external/cwe/cwe-079"],
                        },
                        "defaultConfiguration": {"level": "error"},
                    }],
                }],
            },
            "results": [{
                "ruleId": "py/reflective-xss",
                "message": {"text": "Reflected XSS"},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": "app.py"},
                    "region": {"startLine": 10},
                }}],
            }],
        }],
    }
    findings = _norm(sarif)
    assert len(findings) == 1
    assert findings[0].severity == "high"      # was "info"
    assert findings[0].cwe_id == "CWE-79"       # was None


def test_codeql_command_injection_promotes_to_critical():
    """security-severity >= 9.0 -> critical."""
    sarif = {
        "runs": [{
            "tool": {
                "driver": {"name": "CodeQL"},
                "extensions": [{"rules": [{
                    "id": "py/command-line-injection",
                    "properties": {
                        "security-severity": "9.8",
                        "tags": ["external/cwe/cwe-078"],
                    },
                }]}],
            },
            "results": [{
                "ruleId": "py/command-line-injection",
                "message": {"text": "Command injection"},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": "app.py"}, "region": {"startLine": 5}}}],
            }],
        }],
    }
    findings = _norm(sarif)
    assert findings[0].severity == "critical"
    assert findings[0].cwe_id == "CWE-78"


# --- Bug 2: Semgrep defaultConfiguration.level inheritance -----------------

def _semgrep_result(rule_id: str, default_level: str, cwe_tag: str):
    return {
        "runs": [{
            "tool": {"driver": {"name": "Semgrep OSS", "rules": [{
                "id": rule_id,
                "properties": {"tags": [cwe_tag]},
                "defaultConfiguration": {"level": default_level},
            }]}},
            "results": [{
                # NOTE: no "level" key — exactly like real Semgrep output.
                "ruleId": rule_id,
                "message": {"text": "finding"},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": "x.py"}, "region": {"startLine": 1}}}],
            }],
        }],
    }


def test_semgrep_error_level_becomes_high():
    f = _norm(_semgrep_result(
        "python.flask.security.injection.os-system-injection", "error",
        "CWE-78: OS Command Injection"))
    assert f[0].severity == "high"      # was "info"
    assert f[0].cwe_id == "CWE-78"      # Semgrep "CWE-78: ..." tag format


def test_semgrep_warning_level_becomes_medium():
    f = _norm(_semgrep_result("python.lang.audit.sqli", "warning", "CWE-89: SQL Injection"))
    assert f[0].severity == "medium"
    assert f[0].cwe_id == "CWE-89"


def test_semgrep_note_level_becomes_low():
    f = _norm(_semgrep_result("python.lang.best-practice", "note", "CWE-1004: x"))
    assert f[0].severity == "low"


# --- Bug 3: missing level + no rule -> medium, not info --------------------

def test_unresolved_level_defaults_to_medium_not_info():
    """Result with no level and no matching rule → SARIF spec default
    'warning' → medium (NOT the old silent 'info')."""
    sarif = {
        "runs": [{
            "tool": {"driver": {"name": "Mystery"}},
            "results": [{
                "ruleId": "unknown-thing",
                "message": {"text": "no level, no rule def"},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": "x.py"}, "region": {"startLine": 1}}}],
            }],
        }],
    }
    assert _norm(sarif)[0].severity == "medium"


def test_rule_default_none_is_skipped():
    """A rule configured defaultConfiguration.level=none with no
    security-severity override is a non-problem → skipped."""
    sarif = {
        "runs": [{
            "tool": {"driver": {"name": "T", "rules": [{
                "id": "metric-only",
                "defaultConfiguration": {"level": "none"},
            }]}},
            "results": [{
                "ruleId": "metric-only",
                "message": {"text": "informational metric"},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": "x.py"}, "region": {"startLine": 1}}}],
            }],
        }],
    }
    assert _norm(sarif) == []


def test_explicit_result_level_still_wins():
    """When result.level IS present it overrides defaultConfiguration."""
    sarif = {
        "runs": [{
            "tool": {"driver": {"name": "T", "rules": [{
                "id": "r1", "defaultConfiguration": {"level": "note"}}]}},
            "results": [{
                "ruleId": "r1", "level": "error",
                "message": {"text": "m"},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": "x.py"}, "region": {"startLine": 1}}}],
            }],
        }],
    }
    assert _norm(sarif)[0].severity == "high"  # error wins over note

import pytest

from src.models.schemas import FindingCreate
from src.services.enricher import DataEnricher, _OWASP_2021, _SEVERITY_TO_CVSS


@pytest.fixture
def enricher():
    return DataEnricher()


def _finding(**kwargs) -> FindingCreate:
    defaults = dict(
        artifact_id=1,
        tool="semgrep",
        rule_id="test-rule",
        severity="high",
        message="test message",
        file_path="src/app.py",
    )
    defaults.update(kwargs)
    return FindingCreate(**defaults)


# ---------------------------------------------------------------------------
# CWE enrichment
# ---------------------------------------------------------------------------

def test_enrich_adds_cwe_name(enricher):
    f = _finding(cwe_id="CWE-89")
    result = enricher.enrich(f)
    assert result.raw_data.get("cwe_name") is not None
    assert "SQL" in result.raw_data["cwe_name"]


def test_enrich_no_cwe_no_name(enricher):
    f = _finding(cwe_id=None)
    result = enricher.enrich(f)
    assert "cwe_name" not in (result.raw_data or {})


def test_enrich_invalid_cwe_no_crash(enricher):
    f = _finding(cwe_id="CWE-INVALID")
    result = enricher.enrich(f)
    assert result is not None


# ---------------------------------------------------------------------------
# OWASP category enrichment
# ---------------------------------------------------------------------------

def test_enrich_adds_owasp_category(enricher):
    f = _finding(cwe_id="CWE-89")  # SQL Injection → A03
    result = enricher.enrich(f)
    assert "A03:2021" in result.raw_data.get("owasp_category", "")


def test_enrich_cwe_without_owasp_mapping(enricher):
    # CWE-1 has no OWASP mapping in our table
    f = _finding(cwe_id="CWE-1")
    result = enricher.enrich(f)
    assert "owasp_category" not in (result.raw_data or {})


@pytest.mark.parametrize("cwe_id,expected_prefix", [
    ("CWE-79", "A03"),   # XSS → Injection
    ("CWE-287", "A07"),  # Auth failure
    ("CWE-918", "A10"),  # SSRF
    ("CWE-532", "A09"),  # Logging
])
def test_owasp_category_mapping(enricher, cwe_id, expected_prefix):
    f = _finding(cwe_id=cwe_id)
    result = enricher.enrich(f)
    assert result.raw_data["owasp_category"].startswith(expected_prefix)


# ---------------------------------------------------------------------------
# CVSS score enrichment
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("severity,expected_score", [
    ("critical", 9.5),
    ("high", 7.5),
    ("medium", 5.0),
    ("low", 2.0),
    ("info", 0.0),
])
def test_enrich_maps_severity_to_cvss(enricher, severity, expected_score):
    f = _finding(severity=severity, cvss_score=None)
    result = enricher.enrich(f)
    assert result.cvss_score == expected_score


def test_enrich_preserves_existing_cvss(enricher):
    f = _finding(severity="high", cvss_score=6.3)
    result = enricher.enrich(f)
    assert result.cvss_score == 6.3


# ---------------------------------------------------------------------------
# Field preservation
# ---------------------------------------------------------------------------

def test_enrich_preserves_original_fields(enricher):
    f = _finding(rule_id="my-rule", message="original msg", line_number=99)
    result = enricher.enrich(f)
    assert result.rule_id == "my-rule"
    assert result.message == "original msg"
    assert result.line_number == 99
    assert result.artifact_id == 1


def test_enrich_merges_existing_raw_data(enricher):
    f = _finding(cwe_id="CWE-89", raw_data={"dedup_hash": "abc123"})
    result = enricher.enrich(f)
    assert result.raw_data["dedup_hash"] == "abc123"
    assert "cwe_name" in result.raw_data

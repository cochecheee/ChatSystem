import pytest
from pydantic import ValidationError

from src.services.llm.schemas import AnalysisOutput


def _valid_data(**overrides):
    base = {
        "vulnerability_id": "CVE-001",
        "explanation_vi": "Giải thích",
        "impact_vi": "Tác động",
        "remediation_diff": "--- a\n+++ b",
        "severity": "HIGH",
        "cwe_reference": "CWE-89",
        "confidence": "HIGH",
    }
    base.update(overrides)
    return base


def test_valid_output():
    out = AnalysisOutput(**_valid_data())
    assert out.severity == "HIGH"
    assert out.confidence == "HIGH"


def test_severity_normalized_to_uppercase():
    out = AnalysisOutput(**_valid_data(severity="high"))
    assert out.severity == "HIGH"


def test_confidence_normalized_to_uppercase():
    out = AnalysisOutput(**_valid_data(confidence="medium"))
    assert out.confidence == "MEDIUM"


def test_invalid_severity_defaults_to_medium():
    out = AnalysisOutput(**_valid_data(severity="EXTREME"))
    assert out.severity == "MEDIUM"


def test_invalid_confidence_defaults_to_low():
    out = AnalysisOutput(**_valid_data(confidence="CERTAIN"))
    assert out.confidence == "LOW"


def test_missing_required_field_raises():
    data = _valid_data()
    del data["explanation_vi"]
    with pytest.raises(ValidationError):
        AnalysisOutput(**data)

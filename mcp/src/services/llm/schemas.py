from pydantic import BaseModel, field_validator


class AnalysisOutput(BaseModel):
    vulnerability_id: str
    explanation_vi: str
    impact_vi: str
    remediation_diff: str
    severity: str
    cwe_reference: str
    confidence: str

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        allowed = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
        upper = v.upper()
        if upper not in allowed:
            return "MEDIUM"
        return upper

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: str) -> str:
        allowed = {"HIGH", "MEDIUM", "LOW"}
        upper = v.upper()
        if upper not in allowed:
            return "LOW"
        return upper

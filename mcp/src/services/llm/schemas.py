from pydantic import BaseModel, field_validator


class AnalysisOutput(BaseModel):
    vulnerability_id: str
    explanation_vi: str
    impact_vi: str
    remediation_diff: str
    severity: str
    cwe_reference: str
    confidence: str
    # V4.2 — false-positive assessment (grounded in the fetched source) so the
    # developer knows whether this is worth digging into before fixing.
    # HIGH = likely a false positive / not exploitable.
    false_positive_likelihood: str = "LOW"
    false_positive_reason: str = ""

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

    @field_validator("false_positive_likelihood")
    @classmethod
    def validate_fp(cls, v: str) -> str:
        allowed = {"HIGH", "MEDIUM", "LOW"}
        upper = (v or "").upper()
        return upper if upper in allowed else "LOW"


# ---------------------------------------------------------------------------
# V4.3 — "lỗi này có thật không?" investigation (data-flow reasoning + evidence)
#
# A separate structured output from `AnalysisOutput`: the model traces the
# finding's local data flow over the REAL fetched source and returns a verdict
# (TRUE_POSITIVE|FALSE_POSITIVE|UNCERTAIN) backed by step-by-step reasoning,
# where every step cites a real code snippet + line range. Nested lists are fine
# for Gemini `response_schema` (same path as AnalysisOutput). Grounding of the
# citations is computed post-hoc by the service (not reported by the model).
# ---------------------------------------------------------------------------

class CodeRef(BaseModel):
    file: str = ""
    line_start: int = 0
    line_end: int = 0


class ReasoningStep(BaseModel):
    claim_vi: str                       # một câu tiếng Việt cho bước lập luận
    kind: str = ""                      # source | propagation | sink | sanitizer
    code_ref: CodeRef = CodeRef()
    quote: str = ""                     # đoạn code copy nguyên văn từ source

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        allowed = {"source", "propagation", "sink", "sanitizer"}
        low = (v or "").strip().lower()
        return low if low in allowed else ""


class FPInvestigationOutput(BaseModel):
    verdict: str                        # TRUE_POSITIVE | FALSE_POSITIVE | UNCERTAIN
    confidence: str = "LOW"             # HIGH | MEDIUM | LOW
    summary_vi: str = ""
    reasoning_steps: list[ReasoningStep] = []
    false_positive_likelihood: str = "LOW"

    @field_validator("verdict")
    @classmethod
    def validate_verdict(cls, v: str) -> str:
        allowed = {"TRUE_POSITIVE", "FALSE_POSITIVE", "UNCERTAIN"}
        upper = (v or "").strip().upper()
        return upper if upper in allowed else "UNCERTAIN"

    @field_validator("confidence", "false_positive_likelihood")
    @classmethod
    def validate_level(cls, v: str) -> str:
        allowed = {"HIGH", "MEDIUM", "LOW"}
        upper = (v or "").upper()
        return upper if upper in allowed else "LOW"

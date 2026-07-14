import hashlib
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FindingCreate(BaseModel):
    artifact_id: int
    tool: str
    rule_id: str
    severity: str
    message: str
    file_path: str
    line_number: int | None = None
    raw_data: dict[str, Any] | None = None
    cwe_id: str | None = None
    cvss_score: float | None = None
    owasp_class: str | None = None  # V4.4 — OWASP Top-10 class code (e.g. "A03")


class FindingOut(BaseModel):
    id: int
    artifact_id: int
    project_id: int | None = None  # V3.2 — provenance for the UI
    tool: str
    rule_id: str
    severity: str
    message: str
    file_path: str
    line_number: int | None
    normalized_at: datetime | None
    cwe_id: str | None
    cvss_score: float | None
    owasp_class: str | None = None  # V4.4 — OWASP Top-10 class code
    dedup_hash: str | None
    status: str
    raw_data: dict[str, Any] | None
    ai_analysis: dict[str, Any] | None
    justification: str | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    revoke_justification: str | None = None
    revoked_by: str | None = None
    revoked_at: datetime | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str
    github_url: str
    github_owner: str = ""
    github_repo: str = ""
    github_token: str = ""
    gemini_api_key: str = ""
    gemini_model: str = ""
    artifact_profile: str = "github-actions-default"
    polling_workflow_name: str = ""   # empty = match any workflow (artifact profile filters)
    polling_branch: str = "main"
    staging_url: str = ""
    active: bool = True
    # Chỉ để điền sẵn workflow snippet trong integration bundle — KHÔNG lưu vào
    # Project (create_project pop ra trước khi insert). java|python|node|go.
    language: str = "python"


class ProjectUpdate(BaseModel):
    """Partial update — only fields user wants to change."""
    name: str | None = None
    github_owner: str | None = None
    github_repo: str | None = None
    github_token: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    artifact_profile: str | None = None
    polling_workflow_name: str | None = None
    polling_branch: str | None = None
    staging_url: str | None = None
    active: bool | None = None


class MonitorTargetUpdate(BaseModel):
    """V3.7 — set/clear a project's uptime Monitor staging URL."""
    staging_url: str = ""


class ProjectOut(BaseModel):
    id: int
    name: str
    github_url: str
    last_processed_run_id: int | None
    github_owner: str = ""
    github_repo: str = ""
    # NOTE: github_token + gemini_api_key + webhook_token NOT exposed —
    # secrets stay server-side. UI surfaces "configured" booleans instead.
    # The plaintext webhook token is shown ONLY via the
    # /projects/{id}/webhook/rotate response (one-time reveal) and the
    # /projects/{id}/integration owner-only endpoint.
    has_github_token: bool = False
    has_gemini_api_key: bool = False
    has_webhook_token: bool = False
    gemini_model: str = ""
    artifact_profile: str = "github-actions-default"
    polling_workflow_name: str = ""
    polling_branch: str = "main"
    staging_url: str = ""
    active: bool = True
    # V3.6 — gate policy + soft-delete flag
    gate_critical_threshold: int = 0
    gate_high_threshold: int = 5
    archived_at: datetime | None = None

    model_config = {"from_attributes": True}


class IntegrationInfo(BaseModel):
    """Gói one-time trả về khi TẠO project — mọi thứ cần để tích hợp pipeline.

    `webhook_token` (plaintext) chỉ xuất hiện Ở ĐÂY, đúng precedent của
    /webhook/rotate; sau đó ẩn khỏi mọi API response (ProjectOut chỉ có
    `has_webhook_token`). Muốn lấy lại phải rotate.
    """
    project_id: int
    webhook_token: str
    dashboard_url: str
    # [{"name", "value", "required": "true"|"false", "note"}] — `required=false`
    # đánh dấu secret tuỳ chọn (vd NVD_API_KEY); `note` giải thích cách lấy/ý nghĩa.
    secrets_to_set: list[dict[str, str]] = []
    workflow_yaml: str = ""
    note: str = ""


class ProjectCreateOut(ProjectOut):
    """Response của POST /projects: ProjectOut + khối integration one-time."""
    integration: IntegrationInfo | None = None


class GatePolicyUpdate(BaseModel):
    """V3.6 — owner-only edit of gate thresholds via PATCH /projects/{id}/gate-policy.

    Set 0 = "don't fail on this severity at all". Practical values:
      critical: 0 (fail on first), 1 (allow 1)
      high:     5 (allow 5), 10 (lenient), 0 (strict)
    """
    critical_threshold: int | None = Field(default=None, ge=0)
    high_threshold: int | None = Field(default=None, ge=0)


# ---------------------------------------------------------------------------
# Artifact processing
# ---------------------------------------------------------------------------

class ProcessRequest(BaseModel):
    github_artifact_id: int
    project_id: int


class ProcessResponse(BaseModel):
    message: str
    db_artifact_id: int
    status: str


class WebhookRunPayload(BaseModel):
    """Body của POST /webhook/pipeline-complete từ CI.

    CI gửi run-metadata.json có nhiều fields — required là `run_id`.
    `repository` (V2.8 multi-tenant) cho phép backend route đúng project;
    nếu thiếu hoặc match nothing → fallback settings.GITHUB_OWNER/REPO.
    """
    run_id: int
    pipeline_status: str = "unknown"
    repository: str | None = None  # "owner/repo" — V2.8 multi-tenant routing key

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# LLM Analysis
# ---------------------------------------------------------------------------

class AnalysisResult(BaseModel):
    finding_id: int
    vulnerability_id: str
    explanation_vi: str
    impact_vi: str
    remediation_diff: str
    severity: str
    cwe_reference: str
    confidence: str
    # V4.2 — false-positive verdict (from the model, grounded in code) +
    # grounding of the fix diff (computed post-hoc, not model-reported).
    false_positive_likelihood: str = "LOW"
    false_positive_reason: str = ""
    grounded: bool = True
    grounded_note: str = ""


# ---------------------------------------------------------------------------
# V4.3 — false-positive investigation ("lỗi này có thật không?"). Persisted in
# finding.raw_data['fp_investigation'] and returned by the chat / /verify path.
# Each step carries a per-step grounding flag computed post-hoc against the real
# source (the model does not report `grounded`), mirroring AnalysisResult.
# ---------------------------------------------------------------------------

class InvestigationStep(BaseModel):
    claim_vi: str
    kind: str = ""
    file: str = ""
    line_start: int = 0
    line_end: int = 0
    quote: str = ""
    grounded: bool = False
    grounded_note: str = ""


class FPInvestigation(BaseModel):
    finding_id: int
    verdict: str                        # TRUE_POSITIVE | FALSE_POSITIVE | UNCERTAIN
    confidence: str = "LOW"
    summary_vi: str = ""
    steps: list[InvestigationStep] = []
    false_positive_likelihood: str = "LOW"
    grounded: bool = True               # overall (>=60% steps grounded)
    grounded_note: str = ""
    source_available: bool = True
    suggested_command: str | None = None   # "/revoke N" (FP) | "/fix N" (TP)


# ---------------------------------------------------------------------------
# ChatOps
# ---------------------------------------------------------------------------

class CommandRequest(BaseModel):
    command: str                        # "/explain", "/fix", "/approve", etc.
    finding_id: int | None = None
    run_id: int | None = None
    justification: str | None = None
    # /feedback — free-form text comment about an AI analysis
    feedback_text: str | None = None
    # /status, /results — optional repo override (defaults to configured repo)
    repo: str | None = None


class CommandResponse(BaseModel):
    status: str                         # "ok" | "error"
    message: str
    data: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TokenRequest(BaseModel):
    username: str
    password: str
    # V3.8: role is no longer client-supplied — it's read from the users
    # table after the password verifies, so the JWT `role` claim can't be
    # forged. Kept as an ignored optional field for backward-compatible
    # request bodies (older clients/tests that still send it).
    role: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def compute_dedup_hash(rule_id: str, file_path: str, message: str) -> str:
    raw = f"{rule_id}:{file_path}:{message}"
    return hashlib.sha256(raw.encode()).hexdigest()

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


class FindingOut(BaseModel):
    id: int
    artifact_id: int
    tool: str
    rule_id: str
    severity: str
    message: str
    file_path: str
    line_number: int | None
    normalized_at: datetime | None
    cwe_id: str | None
    cvss_score: float | None
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
    polling_workflow_name: str = "CI Workflow"
    polling_branch: str = "main"
    active: bool = True


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
    active: bool | None = None


class ProjectOut(BaseModel):
    id: int
    name: str
    github_url: str
    last_processed_run_id: int | None
    github_owner: str = ""
    github_repo: str = ""
    # NOTE: github_token + gemini_api_key NOT exposed — secrets stay
    # server-side. UI surfaces "configured" booleans instead.
    has_github_token: bool = False
    has_gemini_api_key: bool = False
    gemini_model: str = ""
    artifact_profile: str = "github-actions-default"
    polling_workflow_name: str = "CI Workflow"
    polling_branch: str = "main"
    active: bool = True

    model_config = {"from_attributes": True}


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

    CI gửi run-metadata.json có nhiều fields — chỉ cần run_id,
    các field khác được ignore tự động.
    """
    run_id: int
    pipeline_status: str = "unknown"

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
    role: str = "developer"             # "developer" | "security_lead" | "admin"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def compute_dedup_hash(rule_id: str, file_path: str, message: str) -> str:
    raw = f"{rule_id}:{file_path}:{message}"
    return hashlib.sha256(raw.encode()).hexdigest()

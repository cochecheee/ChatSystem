import hashlib
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sarif_pydantic import Sarif as SarifLog  # noqa: F401 — re-exported for SARIF validation


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

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str
    github_url: str


class ProjectOut(BaseModel):
    id: int
    name: str
    github_url: str
    last_processed_run_id: int | None

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


def compute_dedup_hash(rule_id: str, file_path: str, message: str) -> str:
    raw = f"{rule_id}:{file_path}:{message}"
    return hashlib.sha256(raw.encode()).hexdigest()

import enum
from datetime import datetime, UTC

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, JSON, String, Text

# Timezone-aware DateTime singleton — passed to every `mapped_column(DT_TZ, ...)`
# so Postgres column type is TIMESTAMP WITH TIME ZONE. asyncpg refuses to
# bind a tz-aware Python datetime to a naive TIMESTAMP column, so without
# this every INSERT raises "can't subtract offset-naive and offset-aware".
# SQLite ignores timezone=True (stored as text), so dev still works.
DT_TZ = DateTime(timezone=True)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base


class ArtifactStatus(str, enum.Enum):
    pending = "pending"
    processed = "processed"
    failed = "failed"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    github_url: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DT_TZ, default=lambda: datetime.now(UTC))
    # GitHub workflow run IDs are 64-bit (~25B as of 2026). On Postgres,
    # SQLAlchemy Integer = INT4 (max 2.1B) → "integer out of range" on insert.
    # SQLite hid this because it stores integers dynamically up to 64-bit.
    last_processed_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Multi-tenant config (Day 2). One chat-system instance can serve N
    # repos — each row carries the GitHub creds + AI key + polling and
    # artifact-profile knobs that used to live on the global settings
    # singleton. Plain-text storage is intentional for thesis scope; see
    # PROGRESS.md "credentials" decision.
    github_owner: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    github_repo: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    github_token: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    gemini_api_key: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    gemini_model: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    artifact_profile: Mapped[str] = mapped_column(
        String(64), default="github-actions-default", nullable=False,
    )
    polling_workflow_name: Mapped[str] = mapped_column(String(255), default="CI Workflow", nullable=False)
    polling_branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)
    # Stored as INTEGER (0/1) for SQLite compat; Mapped[int] keeps the
    # type honest so asyncpg doesn't try to coerce bool -> bool to a
    # Postgres INTEGER column, which raises 'invalid input syntax'.
    active: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    artifacts: Mapped[list["Artifact"]] = relationship("Artifact", back_populates="project")

    # Pydantic ProjectOut reads these via from_attributes — keeps secrets
    # off the wire while letting the UI render a "configured" indicator.
    @property
    def has_github_token(self) -> bool:
        return bool(self.github_token)

    @property
    def has_gemini_api_key(self) -> bool:
        return bool(self.gemini_api_key)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    github_artifact_id: Mapped[str] = mapped_column(String(255), nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False)
    github_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default=ArtifactStatus.pending.value, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DT_TZ, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DT_TZ, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    project: Mapped["Project"] = relationship("Project", back_populates="artifacts")
    findings: Mapped[list["Finding"]] = relationship("Finding", back_populates="artifact")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_id: Mapped[int] = mapped_column(Integer, ForeignKey("artifacts.id"), nullable=False)
    tool: Mapped[str] = mapped_column(String(100), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    normalized_at: Mapped[datetime | None] = mapped_column(DT_TZ, nullable=True)
    cwe_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cvss_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    dedup_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending_review", nullable=False)
    ai_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Approval audit trail
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DT_TZ, nullable=True)

    # Revoke audit trail
    revoke_justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DT_TZ, nullable=True)

    artifact: Mapped["Artifact"] = relationship("Artifact", back_populates="findings")


class AppConfig(Base):
    """Key-value store cho dashboard runtime config.

    Keys hiện tại: 'sast_tools', 'gates', 'ai'. Value là JSON object
    free-form — service layer định nghĩa schema cho từng key qua defaults.
    """

    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DT_TZ,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# V2.4 — Monitor + alert
# ---------------------------------------------------------------------------

class UptimeCheck(Base):
    """One ping result against an inheritor staging URL.

    Scheduler writes 1 row every POLLING_INTERVAL_SECONDS. The Monitor tab
    aggregates these into uptime % and a sparkline. Rows older than 7 days
    are pruned in a daily job to keep SQLite small.
    """

    __tablename__ = "uptime_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False)
    target_url: Mapped[str] = mapped_column(String(512), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DT_TZ, default=lambda: datetime.now(UTC), nullable=False, index=True,
    )
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_up: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 if 2xx/3xx
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class Alert(Base):
    """Operational alert raised by the monitor (down event, CVE diff, etc).

    Distinct from Finding — these are runtime events not source-code issues.
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("projects.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    # kind ∈ {"down", "recovered", "cve_new", "deploy_failed"}
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raised_at: Mapped[datetime] = mapped_column(DT_TZ, default=lambda: datetime.now(UTC), nullable=False, index=True,
    )
    notified_at: Mapped[datetime | None] = mapped_column(DT_TZ, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DT_TZ, nullable=True)

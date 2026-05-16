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


class CommandFeedback(Base):
    """User feedback for /feedback ChatOps command — báo cáo tiến độ ch.4.3.

    Stores natural-language quality feedback against an AI-analyzed finding
    so prompts/models can be tuned later. Optional finding_id lets users
    submit general feedback as well.
    """

    __tablename__ = "command_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finding_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("findings.id"), nullable=True)
    submitted_by: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DT_TZ, default=lambda: datetime.now(UTC), nullable=False,
    )


class ProjectMember(Base):
    """V3.0 — per-project RBAC.

    Maps a username (carried in the JWT `sub` claim) to a role for one
    project. The composite primary key prevents double-membership and
    lets the membership lookup hit an index. Roles form a 4-level lattice:
        viewer < developer < security_lead < owner
    Only `owner` may add/remove members. Global `admin` (encoded in the
    JWT `role` claim) bypasses every check — operator override for demo /
    incident response. Gated by settings.RBAC_PER_PROJECT.
    """

    __tablename__ = "project_members"

    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), primary_key=True,
    )
    # `username` (not user_id) — the system has no `users` table; identity
    # comes from the JWT, issued via /api/chat/auth/token. Keeps V3.0
    # additive: no schema-level migration of existing users needed.
    username: Mapped[str] = mapped_column(String(255), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")
    created_at: Mapped[datetime] = mapped_column(
        DT_TZ, default=lambda: datetime.now(UTC), nullable=False,
    )


class SuppressionRule(Base):
    """V3.1 Tier 2 — pattern-based false-positive suppression.

    When ingest produces a Finding that matches an active rule, the
    Finding's status is auto-set to REVOKED with audit pointing back at
    the rule id. Unlike Tier 1's per-dedup-hash inherit, this catches
    NEW findings that resemble triaged ones (same rule on a file under
    same directory, etc).

    Match semantics: `rule_id == finding.rule_id` (or NULL = match all)
    AND fnmatch(finding.file_path, file_glob) (or NULL = any)
    AND tool == finding.tool (or NULL)
    AND severity rank <= severity_max (or NULL = any).

    `expires_at` lets temp suppressions self-expire (default 90d in API).
    """

    __tablename__ = "suppression_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False, index=True,
    )
    rule_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_glob: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    tool: Mapped[str | None] = mapped_column(String(100), nullable=True)
    severity_max: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DT_TZ, default=lambda: datetime.now(UTC), nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DT_TZ, nullable=True)


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

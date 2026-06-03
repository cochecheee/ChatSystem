import enum
from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, DateTime, Float, ForeignKey, Integer, String, Text

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
    # V3.6 — soft delete. archived_at IS NOT NULL hides project from default
    # listings but preserves findings/runs for audit. Reactivate via API.
    archived_at: Mapped[datetime | None] = mapped_column(DT_TZ, nullable=True)
    # GitHub workflow run IDs are 64-bit (~25B as of 2026). On Postgres,
    # SQLAlchemy Integer = INT4 (max 2.1B) → "integer out of range" on insert.
    # SQLite hid this because it stores integers dynamically up to 64-bit.
    last_processed_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # V3.6 — per-project gate policy. CI gate (/findings/gate-count) reads
    # these thresholds and decides pass/fail. Default = 0 critical / 5 high
    # matches the sast-action defaults so behavior is identical until an
    # owner edits them. Lifting threshold = team accepts more risk; an audit
    # log row is written on every change.
    gate_critical_threshold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gate_high_threshold: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

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

    # V3.5 — Per-project webhook token. Replaces the global CI_WEBHOOK_TOKEN
    # env when set: incoming `Authorization: Bearer <token>` is matched
    # against this column to pick the owning project, so a CI from repo A
    # can't push findings to project B by spoofing `body.repository`. When
    # empty, the global token (settings.CI_WEBHOOK_TOKEN) is honored as
    # legacy fallback. Encrypted via Fernet when FERNET_KEY is set.
    webhook_token: Mapped[str] = mapped_column(String(500), default="", nullable=False)

    artifacts: Mapped[list["Artifact"]] = relationship("Artifact", back_populates="project")

    # Pydantic ProjectOut reads these via from_attributes — keeps secrets
    # off the wire while letting the UI render a "configured" indicator.
    @property
    def has_github_token(self) -> bool:
        return bool(self.github_token)

    @property
    def has_gemini_api_key(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def has_webhook_token(self) -> bool:
        return bool(self.webhook_token)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    github_artifact_id: Mapped[str] = mapped_column(String(255), nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False)
    # V3.6 — first-class PipelineRun. Existing rows keep `github_run_id` as a
    # denormalized cache (still indexed for fast lookup), but new code paths
    # SHOULD prefer `run_id` (FK) so they pull metadata transparently. The
    # migration backfills run_id from (project_id, github_run_id) groups.
    github_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("pipeline_runs.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default=ArtifactStatus.pending.value, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DT_TZ, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DT_TZ, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    project: Mapped["Project"] = relationship("Project", back_populates="artifacts")
    run: Mapped["PipelineRun | None"] = relationship("PipelineRun", back_populates="artifacts")
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

    @property
    def project_id(self) -> int | None:
        """Pydantic FindingOut reads this for V3.2 SMELL-6 — surface the
        finding's owning project without forcing every caller to do a
        Finding -> Artifact -> Project join in their head. Returns None if
        the artifact relationship isn't loaded (lazy access in async code
        would otherwise raise MissingGreenlet)."""
        try:
            return self.artifact.project_id if self.artifact else None
        except Exception:
            return None


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


class PipelineRun(Base):
    """V3.6 — A workflow run is a first-class entity.

    One GitHub Actions workflow run = one row. Captured at webhook time with
    full metadata (branch, sha, actor, conclusion, timing). Artifacts FK in
    via `run_id`. Findings inherit the run via Finding -> Artifact -> Run.

    Why first-class instead of a denormalized `github_run_id` column:
      - Pipelines page can show real history offline (no live GitHub API)
      - Run-over-run diff: which findings were introduced/fixed
      - Trend charts: pass rate / severity over time
      - Per-run AI summary cache key
      - Audit: who triggered this run, when, what conclusion

    Unique key is (project_id, github_run_id) so the same GitHub run id can
    coexist across projects (one repo per project but defense in depth).
    """

    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False, index=True,
    )
    # 64-bit because GitHub run IDs already exceed INT4 max (~2.1B). See the
    # Artifact.github_run_id comment for the same constraint history.
    github_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    github_run_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workflow_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    head_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # GitHub workflow event — "push" | "pull_request" | "workflow_dispatch" | ...
    event: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # GitHub status — "queued" | "in_progress" | "completed"
    status: Mapped[str] = mapped_column(String(50), default="completed", nullable=False)
    # GitHub conclusion — "success" | "failure" | "cancelled" | "timed_out" | "skipped" | None
    conclusion: Mapped[str | None] = mapped_column(String(50), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DT_TZ, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DT_TZ, nullable=True)
    github_run_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DT_TZ, default=lambda: datetime.now(UTC), nullable=False, index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DT_TZ, default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC), nullable=False,
    )

    artifacts: Mapped[list["Artifact"]] = relationship("Artifact", back_populates="run")

    # Composite unique to dedup webhook retries / multi-tenant overlaps.
    from sqlalchemy import UniqueConstraint
    __table_args__ = (
        UniqueConstraint("project_id", "github_run_id", name="uq_pipeline_runs_project_github"),
    )


class WebhookDelivery(Base):
    """V3.6 — append-only log of incoming webhook deliveries for dedup + audit.

    GitHub Actions issues `X-GitHub-Delivery: <uuid>` on every webhook (or
    the sast-action composite synthesizes one). When the same delivery
    arrives twice (network glitch, GitHub retry, replay attack), we look it
    up here BEFORE running process_run — if already seen, return 200 OK and
    skip the work. Without this, every retry causes a second ingest cycle
    that explodes the findings count via re-normalization.

    The body_sha256 column lets us also detect tampering: if the same
    delivery id arrives with a different body hash, log + reject.
    """

    __tablename__ = "webhook_deliveries"

    # Use the delivery UUID as PK so duplicate inserts fail fast.
    delivery_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=True, index=True,
    )
    github_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DT_TZ, default=lambda: datetime.now(UTC), nullable=False, index=True,
    )
    body_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # "accepted" | "duplicate" | "rejected_signature" | "rejected_unknown_project"
    outcome: Mapped[str] = mapped_column(String(40), default="accepted", nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditLog(Base):
    """V3.6 — append-only audit trail.

    Distinct from finding.{approved_by, revoked_by} fields because:
      - those fields disappear when the finding row is deleted
      - they capture only the LAST action; a re-approve / un-revoke wipes
        the previous decision

    Every privileged action writes a row here: project create/archive,
    member add/remove, gate threshold change, finding approve/revoke,
    suppression rule create, webhook token rotate. Read-only history view
    in the UI's Settings tab.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # "approve" | "revoke" | "create_project" | "archive_project" |
    # "add_member" | "remove_member" | "rotate_webhook_token" |
    # "set_gate_threshold" | "create_suppression" | "delete_suppression"
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Optional scoping fields. project_id always set for project-scoped
    # actions; target_kind/target_id identify the row touched (e.g.
    # target_kind="finding", target_id=42).
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    target_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Free-form JSON for before/after snapshots or extra context. Examples:
    #   {"justification": "..."}                    -- approve/revoke
    #   {"old": 0, "new": 2}                        -- gate threshold change
    #   {"username": "alice", "role": "owner"}      -- member add
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DT_TZ, default=lambda: datetime.now(UTC), nullable=False, index=True,
    )


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

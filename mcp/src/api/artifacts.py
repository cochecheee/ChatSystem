from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.db import AsyncSessionLocal, get_session
from ..models.entities import Artifact, Finding, Project, WebhookDelivery
from ..models.schemas import (
    FindingOut,
    GatePolicyUpdate,
    ProcessRequest,
    ProcessResponse,
    ProjectCreate,
    ProjectOut,
    WebhookRunPayload,
)
from ..core.auth import User, allowed_project_ids, get_current_user, require_read_access, security as _bearer_auth
from ..repositories import ArtifactRepository, FindingRepository, ProjectRepository
from ..services.github_client import GitHubClient
from ..services.processor import SecurityProcessor


# V3.0 — helpers for member CRUD endpoints. `_optional` returns None
# instead of raising when no JWT is provided so legacy callers still work.
async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_auth),
) -> User | None:
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


async def get_current_user_required(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_auth),
) -> User:
    return await get_current_user(credentials)


from pydantic import BaseModel  # noqa: E402 — local to this module


class MemberUpsert(BaseModel):
    username: str
    role: str  # viewer | developer | security_lead | owner

router = APIRouter()


def get_github_client() -> GitHubClient:
    return GitHubClient()

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)  # Authorization: Bearer <token>


async def require_api_key(api_key: str | None = Depends(_api_key_header)) -> None:
    expected = settings.CI_API_KEY
    if not expected:
        return  # CI_API_KEY not set → auth disabled (dev / test mode)
    if api_key != expected:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------

def get_processor() -> SecurityProcessor:
    return SecurityProcessor(session_factory=AsyncSessionLocal)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(
    body: ProjectCreate,
    session: AsyncSession = Depends(get_session),
) -> Project:
    """Tạo project với full credentials (V2.8 P7).

    Trước đây chỉ persist name + github_url; các field credentials
    (github_owner/repo/token, gemini_*) bị drop silent → POST /projects
    không bao giờ wire multi-tenant đúng. Giờ persist tất cả 9 field.

    Secrets (`github_token`, `gemini_api_key`) sẽ được Fernet-encrypt khi
    `FERNET_KEY` set ở Phase A1 — hiện vẫn plaintext (single-tenant
    deployment chấp nhận theo decision log [.planning/REQUIREMENTS.md]).
    `active=False` map sang INTEGER 0 — Postgres asyncpg không tự coerce.
    """
    repo = ProjectRepository(session)
    fields = body.model_dump(exclude_unset=False)
    # Bool -> int để khớp Mapped[int] cột active
    fields["active"] = 1 if fields.get("active", True) else 0
    return await repo.create(**fields)


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(
    session: AsyncSession = Depends(get_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    _: User | None = Depends(require_read_access),
) -> list[Project]:
    """List projects. When V3.0 RBAC is on AND a JWT is provided, results
    are filtered to projects the caller has a membership in (admins see all).
    When ANONYMOUS_READ_ENABLED is on, anonymous callers see everything; when
    off (V3.3 default), all callers must present a JWT.
    """
    all_projects = await ProjectRepository(session).list_all()
    if not settings.RBAC_PER_PROJECT or credentials is None:
        return all_projects
    # Decode token best-effort; opaque/expired tokens fall back to legacy.
    try:
        from jose import jwt
        payload = jwt.decode(
            credentials.credentials, settings.SECRET_KEY, algorithms=["HS256"],
        )
    except Exception:
        return all_projects
    if payload.get("role") == "admin":
        return all_projects
    raw_m = payload.get("memberships") or {}
    member_ids = {int(k) for k in raw_m.keys()}
    return [p for p in all_projects if p.id in member_ids]


# ---------------------------------------------------------------------------
# V3.0 — Per-project membership management
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/members")
async def list_project_members(
    project_id: int,
    session: AsyncSession = Depends(get_session),
    current: "User" = Depends(get_current_user_optional),
) -> list[dict]:
    """List members of a project. Requires authenticated user; when RBAC
    is on, the caller must have any role on the project (or be admin).
    """
    from ..repositories import ProjectMemberRepository
    project = await ProjectRepository(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    repo = ProjectMemberRepository(session)
    if settings.RBAC_PER_PROJECT and current and current.role != "admin":
        if await repo.get_role(project_id, current.username) is None:
            raise HTTPException(status_code=403, detail="Not a project member")
    members = await repo.list_for_project(project_id)
    return [
        {"username": m.username, "role": m.role, "created_at": m.created_at.isoformat()}
        for m in members
    ]


@router.post("/projects/{project_id}/members", status_code=201)
async def add_project_member(
    project_id: int,
    body: "MemberUpsert",
    session: AsyncSession = Depends(get_session),
    current: "User" = Depends(get_current_user_required),
) -> dict:
    """Add or update a member. Caller must be project `owner` (or global admin)."""
    from ..repositories import ProjectMemberRepository, ROLE_LATTICE
    if body.role not in ROLE_LATTICE:
        raise HTTPException(status_code=400, detail=f"role must be one of {ROLE_LATTICE}")
    project = await ProjectRepository(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    repo = ProjectMemberRepository(session)
    # Authorization: only owner can invite. Admins bypass.
    if current.role != "admin":
        caller_role = await repo.get_role(project_id, current.username)
        if caller_role != "owner":
            raise HTTPException(status_code=403, detail="Only project owner may add members")
    member = await repo.upsert(
        project_id=project_id, username=body.username, role=body.role,
    )
    return {"username": member.username, "role": member.role}


@router.get("/projects/{project_id}/suppressions")
async def list_suppressions(
    project_id: int,
    include_expired: bool = False,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """List suppression rules (V3.1 Tier 2). `include_expired=true` to show all
    rules (history), otherwise only currently-active rules are returned.
    """
    from ..repositories import SuppressionRuleRepository
    project = await ProjectRepository(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    repo = SuppressionRuleRepository(session)
    rules = (
        await repo.list_all_for_project(project_id)
        if include_expired
        else await repo.list_active_for_project(project_id)
    )
    return [
        {
            "id": r.id,
            "rule_id": r.rule_id,
            "file_glob": r.file_glob,
            "tool": r.tool,
            "severity_max": r.severity_max,
            "reason": r.reason,
            "created_by": r.created_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        }
        for r in rules
    ]


class SuppressionCreate(BaseModel):
    reason: str
    rule_id: str | None = None
    file_glob: str | None = None
    tool: str | None = None
    severity_max: str | None = None
    expires_in_days: int | None = 90  # default 90d expiry — temp by design


@router.post("/projects/{project_id}/suppressions", status_code=201)
async def create_suppression(
    project_id: int,
    body: SuppressionCreate,
    session: AsyncSession = Depends(get_session),
    current: User = Depends(get_current_user_required),
) -> dict:
    """Create a suppression rule. Requires security_lead+ role (per-project)
    or global admin. Auto-applied to new findings on next ingest.
    """
    from datetime import timedelta
    from ..repositories import SuppressionRuleRepository, ProjectMemberRepository, role_satisfies

    project = await ProjectRepository(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Authorization: global admin OR project security_lead+
    if current.role != "admin":
        member_role = await ProjectMemberRepository(session).get_role(project_id, current.username)
        if member_role is None or not role_satisfies(member_role, "security_lead"):
            raise HTTPException(
                status_code=403,
                detail="security_lead role (or higher) required on this project",
            )

    expires_at = None
    if body.expires_in_days:
        from datetime import datetime, UTC
        expires_at = datetime.now(UTC) + timedelta(days=body.expires_in_days)

    repo = SuppressionRuleRepository(session)
    rule = await repo.create(
        project_id=project_id,
        reason=body.reason,
        created_by=current.username,
        rule_id=body.rule_id,
        file_glob=body.file_glob,
        tool=body.tool,
        severity_max=body.severity_max,
        expires_at=expires_at,
    )
    return {
        "id": rule.id,
        "reason": rule.reason,
        "expires_at": rule.expires_at.isoformat() if rule.expires_at else None,
    }


@router.delete("/projects/{project_id}/suppressions/{rule_pk}", status_code=204)
async def delete_suppression(
    project_id: int,
    rule_pk: int,
    session: AsyncSession = Depends(get_session),
    current: User = Depends(get_current_user_required),
) -> Response:
    """Delete a suppression rule. Same authorization as create."""
    from ..repositories import SuppressionRuleRepository, ProjectMemberRepository, role_satisfies

    if current.role != "admin":
        member_role = await ProjectMemberRepository(session).get_role(project_id, current.username)
        if member_role is None or not role_satisfies(member_role, "security_lead"):
            raise HTTPException(status_code=403, detail="security_lead role required")

    repo = SuppressionRuleRepository(session)
    rule = await repo.get(rule_pk)
    if rule is None or rule.project_id != project_id:
        raise HTTPException(status_code=404, detail="Suppression rule not found")
    await repo.delete(rule_pk)
    return Response(status_code=204)


@router.delete("/projects/{project_id}/members/{username}", status_code=204)
async def remove_project_member(
    project_id: int,
    username: str,
    session: AsyncSession = Depends(get_session),
    current: "User" = Depends(get_current_user_required),
) -> Response:
    """Remove a member. Caller must be project `owner` or global admin."""
    from ..repositories import ProjectMemberRepository
    repo = ProjectMemberRepository(session)
    if current.role != "admin":
        caller_role = await repo.get_role(project_id, current.username)
        if caller_role != "owner":
            raise HTTPException(status_code=403, detail="Only project owner may remove members")
    removed = await repo.remove(project_id=project_id, username=username)
    if not removed:
        raise HTTPException(status_code=404, detail="Membership not found")
    return Response(status_code=204)


@router.get("/projects/{project_id}/integration")
async def project_integration_snippet(
    project_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current: "User" = Depends(get_current_user_optional),
) -> dict:
    """Snippet để tích hợp 1 project với chat-system.

    Trả webhook URL + GitHub Actions YAML step + curl test. Khi caller là
    `owner` của project (hoặc global admin), token plaintext được nhúng
    vào snippet để copy-paste thẳng vào CI secrets. Caller không có quyền
    chỉ thấy placeholder `<MCP_WEBHOOK_TOKEN>` và phải nhờ owner cấp token.

    Khi project chưa có per-project token, snippet rớt về placeholder
    có ghi chú dùng `CI_WEBHOOK_TOKEN` legacy — UI sẽ nhắc owner bấm
    "Rotate webhook token" để sinh mới.
    """
    project = await ProjectRepository(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Owner / admin gets the plaintext token; everyone else gets the placeholder.
    can_reveal = False
    if current is not None:
        if current.role == "admin":
            can_reveal = True
        else:
            role = None
            # JWT carries a membership snapshot (V3.0) — trust it first.
            if current.memberships is not None:
                role = current.memberships.get(project_id)
            if role is None:
                from ..repositories import ProjectMemberRepository
                role = await ProjectMemberRepository(session).get_role(
                    project_id, current.username,
                )
            can_reveal = role == "owner"

    # Build base URL từ request — phù hợp cả local dev (localhost:8000)
    # lẫn deploy qua tunnel/proxy (Host header).
    scheme = request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    base = f"{scheme}://{host}"
    webhook_url = f"{base}/webhook/pipeline-complete"

    secret_token_name = "MCP_WEBHOOK_TOKEN"
    secret_url_name = "MCP_GATEWAY_URL"

    # The placeholder substituted into the YAML snippet. Owners see the real
    # token only via the `webhook_token` JSON field (separate from snippet)
    # so they can copy it into the target-repo secrets store. The snippet
    # itself always references `${{ secrets.MCP_WEBHOOK_TOKEN }}` — never
    # inlines the token. This avoids accidentally pasting a secret into
    # a public PR description.

    yaml_step = (
        "- name: Notify chat-system\n"
        "  if: always()\n"
        "  env:\n"
        f"    {secret_url_name}:   ${{{{ secrets.{secret_url_name} }}}}\n"
        f"    {secret_token_name}: ${{{{ secrets.{secret_token_name} }}}}\n"
        "  run: |\n"
        f"    curl -f -s -X POST \"${{{secret_url_name}}}/webhook/pipeline-complete\" \\\n"
        "      -H \"Content-Type: application/json\" \\\n"
        f"      -H \"Authorization: Bearer ${{{secret_token_name}}}\" \\\n"
        "      --max-time 20 \\\n"
        "      -d \"{\\\"run_id\\\": ${{ github.run_id }}, \\\"pipeline_status\\\": \\\"passed\\\"}\"\n"
        "  continue-on-error: true\n"
    )

    curl_test = (
        f"curl -i -X POST \"{webhook_url}\" \\\n"
        "  -H \"Content-Type: application/json\" \\\n"
        f"  -H \"Authorization: Bearer <{secret_token_name}>\" \\\n"
        "  -d '{\"run_id\": 1, \"pipeline_status\": \"test\"}'"
    )

    return {
        "project_id": project.id,
        "project_name": project.name,
        "github_url": project.github_url,
        "webhook_url": webhook_url,
        "auth_required": bool(settings.CI_WEBHOOK_TOKEN) or bool(project.webhook_token),
        "has_project_token": bool(project.webhook_token),
        "webhook_token": project.webhook_token if (can_reveal and project.webhook_token) else None,
        "token_visible": can_reveal,
        "secrets_to_set_in_target_repo": [
            {"name": secret_url_name, "value_hint": webhook_url},
            {
                "name": secret_token_name,
                "value_hint": (
                    "Use the project's webhook_token (see above) if set; otherwise "
                    "the global CI_WEBHOOK_TOKEN from chat-system .env."
                ),
            },
        ],
        "github_actions_yaml_step": yaml_step,
        "manual_test_curl": curl_test,
        "docs": "/docs/webhook-schema.md",
    }


@router.post("/projects/{project_id}/webhook/rotate")
async def rotate_webhook_token(
    project_id: int,
    session: AsyncSession = Depends(get_session),
    current: "User" = Depends(get_current_user_required),
) -> dict:
    """Generate a fresh per-project webhook token. Only `owner` or `admin`.

    Returns the new plaintext token ONCE in the response so the caller can
    copy it into the CI secrets store. After this call the token is only
    visible to owners via `/projects/{id}/integration` (because that
    endpoint re-fetches it from DB).

    Rotating invalidates the previous token immediately — any CI still
    using the old value starts getting 403 on the next webhook call.
    """
    import secrets as _secrets

    project = await ProjectRepository(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # owner / admin gate
    if current.role != "admin":
        role = None
        if current.memberships is not None:
            role = current.memberships.get(project_id)
        if role is None:
            from ..repositories import ProjectMemberRepository
            role = await ProjectMemberRepository(session).get_role(
                project_id, current.username,
            )
        if role != "owner":
            raise HTTPException(
                status_code=403,
                detail="Only project owner (or global admin) can rotate the webhook token",
            )

    # 32 bytes URL-safe → ~43 char token. Enough entropy to defeat guessing.
    new_token = _secrets.token_urlsafe(32)
    await ProjectRepository(session).update(project, {"webhook_token": new_token})
    # V3.6 — audit row for rotation
    from ..repositories.audit_log_repo import write_audit
    await write_audit(
        session, actor=current.username, action="rotate_webhook_token",
        project_id=project_id, target_kind="project", target_id=project_id,
    )
    return {
        "project_id": project_id,
        "webhook_token": new_token,
        "message": "Save this token now — it will be hidden from API responses after this call.",
    }


@router.patch("/projects/{project_id}/gate-policy")
async def update_gate_policy(
    project_id: int,
    body: "GatePolicyUpdate",
    session: AsyncSession = Depends(get_session),
    current: "User" = Depends(get_current_user_required),
) -> dict:
    """V3.6 — set per-project gate thresholds.

    Owner / global admin only. Audit row written with `{"old": {...},
    "new": {...}}` so policy history can be replayed.
    """
    from ..repositories.audit_log_repo import write_audit

    project = await ProjectRepository(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if current.role != "admin":
        role = None
        if current.memberships is not None:
            role = current.memberships.get(project_id)
        if role is None:
            from ..repositories import ProjectMemberRepository
            role = await ProjectMemberRepository(session).get_role(
                project_id, current.username,
            )
        if role != "owner":
            raise HTTPException(
                status_code=403,
                detail="Only project owner (or global admin) can change gate policy",
            )

    old = {
        "critical_threshold": project.gate_critical_threshold,
        "high_threshold": project.gate_high_threshold,
    }
    updates: dict = {}
    if body.critical_threshold is not None:
        updates["gate_critical_threshold"] = body.critical_threshold
    if body.high_threshold is not None:
        updates["gate_high_threshold"] = body.high_threshold

    if not updates:
        return {
            "project_id": project_id,
            "critical_threshold": project.gate_critical_threshold,
            "high_threshold": project.gate_high_threshold,
            "changed": False,
        }

    await ProjectRepository(session).update(project, updates)
    new = {
        "critical_threshold": project.gate_critical_threshold,
        "high_threshold": project.gate_high_threshold,
    }
    await write_audit(
        session, actor=current.username, action="set_gate_threshold",
        project_id=project_id, target_kind="project", target_id=project_id,
        payload={"old": old, "new": new},
    )
    await session.commit()
    return {"project_id": project_id, **new, "changed": True}


@router.post("/projects/{project_id}/archive", status_code=200)
async def archive_project(
    project_id: int,
    session: AsyncSession = Depends(get_session),
    current: "User" = Depends(get_current_user_required),
) -> dict:
    """V3.6 — soft delete. Sets archived_at; project hidden from default lists
    but findings/runs preserved. Owner / admin only. Reverse via /unarchive.
    """
    from datetime import datetime as _dt, UTC as _UTC
    from ..repositories.audit_log_repo import write_audit

    project = await ProjectRepository(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if current.role != "admin":
        role = current.memberships.get(project_id) if current.memberships else None
        if role is None:
            from ..repositories import ProjectMemberRepository
            role = await ProjectMemberRepository(session).get_role(project_id, current.username)
        if role != "owner":
            raise HTTPException(status_code=403, detail="Only owner/admin may archive")
    if project.archived_at is None:
        await ProjectRepository(session).update(project, {"archived_at": _dt.now(_UTC)})
        await write_audit(
            session, actor=current.username, action="archive_project",
            project_id=project_id, target_kind="project", target_id=project_id,
        )
        await session.commit()
    return {"project_id": project_id, "archived_at": project.archived_at.isoformat()
            if project.archived_at else None}


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Xoá project + cascade delete artifacts/findings.

    Hard delete — kept for admin-only / cleanup scripts (no auth gate here
    because legacy test suite + cleanup tooling rely on the unauthenticated
    contract). Prefer POST /projects/{id}/archive (V3.6 soft delete) for
    normal "remove this project" flows.
    """
    project_repo = ProjectRepository(session)
    artifact_repo = ArtifactRepository(session)
    finding_repo = FindingRepository(session)

    project = await project_repo.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    artifacts = await artifact_repo.list_for_project(project_id)
    artifact_ids = [a.id for a in artifacts]
    await finding_repo.delete_by_artifact_ids(artifact_ids)
    await artifact_repo.delete_by_ids(artifact_ids)
    await project_repo.delete(project)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# GitHub browser — inspect runs & artifacts without leaving Swagger UI
# ---------------------------------------------------------------------------

@router.get("/github/runs", summary="List recent workflow runs from GitHub")
async def list_github_runs(
    branch: str = "",
    status: str = "",
    project_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    github: GitHubClient = Depends(get_github_client),
    user: User | None = Depends(require_read_access),
) -> list[dict]:
    """Return recent workflow runs for the configured repo.
    Use the `id` field as input for **GET /github/runs/{run_id}/artifacts**.

    `?project_id=` (V2.9): dùng credentials per-project thay vì env. 404 nếu
    project không tồn tại.
    V3.3: khi RBAC on + non-admin, project_id phải nằm trong memberships.
    """
    scope_ids = allowed_project_ids(user)
    if scope_ids is not None and project_id is not None and project_id not in scope_ids:
        raise HTTPException(
            status_code=403,
            detail=f"Project {project_id} not in your memberships",
        )
    if project_id is not None:
        project = await ProjectRepository(session).get(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        github = GitHubClient.for_project(project)
    try:
        return await github.list_workflow_runs(
            workflow_name="",
            branch=branch,
            status=status,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}")


@router.get(
    "/github/runs/{run_id}/artifacts",
    summary="List artifacts for a workflow run",
)
async def list_github_artifacts(
    run_id: int,
    github: GitHubClient = Depends(get_github_client),
    _: User | None = Depends(require_read_access),
) -> list[dict]:
    """Return artifacts for the given workflow run.
    Use the `id` field as `github_artifact_id` in **POST /artifacts/process**.
    """
    try:
        return await github.list_artifacts(run_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {exc}")


# ---------------------------------------------------------------------------
# Artifact processing
# ---------------------------------------------------------------------------

@router.post(
    "/artifacts/process",
    response_model=ProcessResponse,
    status_code=202,
    dependencies=[Depends(require_api_key)],
)
async def process_artifact(
    body: ProcessRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    processor: SecurityProcessor = Depends(get_processor),
) -> ProcessResponse:
    project_repo = ProjectRepository(session)
    if (await project_repo.get(body.project_id)) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    artifact_repo = ArtifactRepository(session)
    artifact = await artifact_repo.create(
        github_artifact_id=str(body.github_artifact_id),
        project_id=body.project_id,
        status="pending",
    )

    background_tasks.add_task(
        processor.process_artifact,
        artifact.id,
        body.github_artifact_id,
    )

    return ProcessResponse(
        message="Processing started",
        db_artifact_id=artifact.id,
        status="pending",
    )


# ---------------------------------------------------------------------------
# Webhook — CI pipeline calls this when a run completes
# ---------------------------------------------------------------------------

@router.post("/webhook/pipeline-complete", status_code=202)
async def webhook_pipeline_complete(
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Receive notification from CI after a workflow run completes.

    Auth precedence (V3.6):
      1. HMAC `X-Hub-Signature-256: sha256=<hex>` against the body using
         `Project.webhook_token` as secret. Match wins — routes to the
         owning project regardless of body.repository.
      2. Legacy Bearer per-project token (V3.5). Sast-action runners that
         haven't migrated to HMAC mode keep working.
      3. Legacy global `CI_WEBHOOK_TOKEN` (V3.x). Routes by body.repository
         or env GITHUB_OWNER/REPO fallback.

    Replay protection (V3.6): every accepted delivery is recorded in
    `webhook_deliveries` keyed by `X-GitHub-Delivery` header (UUID).
    Same delivery_id seen twice returns 200 with `outcome=duplicate`
    and skips the work.
    """
    import logging
    import uuid as _uuid
    from ..core.webhook_security import (
        record_delivery, verify_signature_against_any_project,
    )
    from ..models.schemas import WebhookRunPayload as _Payload

    log = logging.getLogger(__name__)

    raw_body = await request.body()
    try:
        body = _Payload.model_validate_json(raw_body) if raw_body else _Payload(run_id=0)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid body: {exc}")

    # --- Replay dedup ---
    delivery_id = (
        request.headers.get("x-github-delivery")
        or request.headers.get("x-mcp-delivery")
        or str(_uuid.uuid4())  # synthesize when caller didn't send one
    )
    from sqlalchemy import select
    existing = await session.execute(
        select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery_id)
    )
    if existing.scalar_one_or_none() is not None:
        log.info("Webhook delivery %s is duplicate — skipping", delivery_id)
        return {
            "status": "accepted", "outcome": "duplicate",
            "run_id": body.run_id, "delivery_id": delivery_id,
        }

    project_repo = ProjectRepository(session)
    project = None
    auth_mode: str | None = None

    # --- Auth path 1: HMAC (V3.6 preferred) ---
    sig_header = (
        request.headers.get("x-hub-signature-256")
        or request.headers.get("x-mcp-signature-256")
    )
    if sig_header:
        sig_result = await verify_signature_against_any_project(
            session, raw_body, sig_header,
        )
        if sig_result.outcome == "valid":
            project = await project_repo.get(sig_result.matched_project_id)
            auth_mode = "hmac"
            log.info(
                "Webhook authenticated via HMAC (project_id=%d, delivery=%s)",
                project.id, delivery_id,
            )
        elif sig_result.outcome == "invalid":
            await record_delivery(
                session, delivery_id=delivery_id, project_id=None,
                github_run_id=body.run_id, body=raw_body,
                outcome="rejected_signature",
                detail="HMAC mismatch",
            )
            await session.commit()
            raise HTTPException(status_code=403, detail="Invalid HMAC signature")

    # --- Auth path 2: legacy bearer (V3.5 per-project token) ---
    if project is None:
        webhook_token = credentials.credentials if credentials else None
        if webhook_token:
            project = await project_repo.find_by_webhook_token(webhook_token)
            if project is not None:
                auth_mode = "bearer_per_project"
                log.info(
                    "Webhook authenticated via per-project Bearer "
                    "(project_id=%d, delivery=%s)", project.id, delivery_id,
                )

    # --- Auth path 3: legacy global ---
    if project is None:
        webhook_token = credentials.credentials if credentials else None
        if settings.CI_WEBHOOK_TOKEN:
            if webhook_token != settings.CI_WEBHOOK_TOKEN:
                await record_delivery(
                    session, delivery_id=delivery_id, project_id=None,
                    github_run_id=body.run_id, body=raw_body,
                    outcome="rejected_signature",
                    detail="No valid auth (HMAC/bearer/global)",
                )
                await session.commit()
                raise HTTPException(
                    status_code=403, detail="Invalid or missing webhook auth",
                )
            auth_mode = "bearer_global"
            log.info("Webhook authenticated via legacy global token "
                     "(delivery=%s)", delivery_id)

        if settings.MULTI_TENANT_ENABLED and body.repository:
            github_url = f"https://github.com/{body.repository}"
            project = await project_repo.get_by_github_url(github_url)

        if project is None:
            fallback_url = f"https://github.com/{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}"
            project = await project_repo.get_or_create_by_github_url(
                name=f"{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}",
                github_url=fallback_url,
            )

    # --- Record delivery (accepted) + process ---
    await record_delivery(
        session, delivery_id=delivery_id, project_id=project.id,
        github_run_id=body.run_id, body=raw_body, outcome="accepted",
        detail=f"auth={auth_mode}",
    )
    await session.commit()

    processor = SecurityProcessor(session_factory=AsyncSessionLocal)
    background_tasks.add_task(processor.process_run, project.id, body.run_id)

    return {
        "status": "accepted",
        "outcome": "accepted",
        "run_id": body.run_id,
        "project_id": project.id,
        "delivery_id": delivery_id,
        "auth_mode": auth_mode,
    }


# ---------------------------------------------------------------------------
# Findings endpoints — extracted to api/findings.py in Phase 1.
# Kept imports above (FindingOut, FindingRepository) because reprocess +
# run-findings below still touch finding rows. See main.py for the mount.
# ---------------------------------------------------------------------------


@router.post("/github/runs/{run_id}/reprocess", status_code=202)
async def reprocess_run(
    run_id: int,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Wipe existing findings/artifacts for a run and reprocess from GitHub.

    Used after fixing the normalizer or pulling in new artifact types — the
    previous artifacts in the DB are stale, so we delete them and re-fetch.
    """
    artifact_repo = ArtifactRepository(session)
    finding_repo = FindingRepository(session)
    project_repo = ProjectRepository(session)

    artifacts = await artifact_repo.list_for_run(run_id)
    project_id: int | None = None
    if artifacts:
        project_id = artifacts[0].project_id
        artifact_ids = [a.id for a in artifacts]
        await finding_repo.delete_by_artifact_ids(artifact_ids)
        await artifact_repo.delete_by_ids(artifact_ids)
        await session.commit()

    if project_id is None:
        github_url = f"https://github.com/{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}"
        project = await project_repo.get_by_github_url(github_url)
        if project is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy project gắn với run này.")
        project_id = project.id

    processor = SecurityProcessor(session_factory=AsyncSessionLocal)
    background_tasks.add_task(processor.process_run, project_id, run_id)
    return {"status": "accepted", "run_id": run_id, "deleted_artifacts": len(artifacts)}


# /github/runs/{run_id}/findings moved to api/findings.py

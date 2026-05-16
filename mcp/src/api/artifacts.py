from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.db import AsyncSessionLocal, get_session
from ..models.entities import Artifact, Finding, Project
from ..models.schemas import (
    FindingOut,
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
) -> dict:
    """Trả config snippet cần thiết để tích hợp 1 project mới với chat-system.

    UI/CLI dùng endpoint này để hiển thị "Cách tích hợp project này":
    - URL webhook
    - Tên secret cần đặt trong GitHub Actions
    - YAML step copy-paste
    - curl command để test thủ công

    KHÔNG trả token thật — UI chỉ render placeholder; admin operator
    set secret bằng tay ở repo target.
    """
    project = await ProjectRepository(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Build base URL từ request — phù hợp cả local dev (localhost:8000)
    # lẫn deploy qua tunnel/proxy (Host header).
    scheme = request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    base = f"{scheme}://{host}"
    webhook_url = f"{base}/webhook/pipeline-complete"

    secret_token_name = "MCP_WEBHOOK_TOKEN"
    secret_url_name = "MCP_GATEWAY_URL"

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
        "auth_required": bool(settings.CI_WEBHOOK_TOKEN),
        "secrets_to_set_in_target_repo": [
            {"name": secret_url_name, "value_hint": webhook_url},
            {
                "name": secret_token_name,
                "value_hint": "<the same MCP_WEBHOOK_TOKEN in chat-system .env>",
            },
        ],
        "github_actions_yaml_step": yaml_step,
        "manual_test_curl": curl_test,
        "docs": "/docs/webhook-schema.md",
    }


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Xoá project + cascade delete artifacts/findings.

    Returns 204 No Content. Returns 404 nếu project không tồn tại.
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
    body: WebhookRunPayload,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Receive notification from CI pipeline after a workflow run completes.

    CI gửi: POST /webhook/pipeline-complete
    Header: Authorization: Bearer <MCP_WEBHOOK_TOKEN>
    Body:   run-metadata.json (có run_id, run_number, repository, ...)

    Routing (V2.8):
      MULTI_TENANT_ENABLED=true + body.repository có giá trị → lookup
        Project theo github_url. Match → dùng project đó.
      Không match hoặc flag off → fallback settings.GITHUB_OWNER/REPO
        (legacy behavior). Log warning để debug.

    CI_WEBHOOK_TOKEN trống → auth disabled (dev mode).
    """
    import logging
    log = logging.getLogger(__name__)

    webhook_token = credentials.credentials if credentials else None
    if settings.CI_WEBHOOK_TOKEN and webhook_token != settings.CI_WEBHOOK_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid or missing webhook token")

    project_repo = ProjectRepository(session)
    project = None

    # Multi-tenant path: lookup by repository field from payload
    if settings.MULTI_TENANT_ENABLED and body.repository:
        github_url = f"https://github.com/{body.repository}"
        project = await project_repo.get_by_github_url(github_url)
        if project is None:
            log.warning(
                "Webhook repository=%r không tìm được project — fallback env",
                body.repository,
            )

    # Fallback / legacy: use env-configured single-tenant project
    if project is None:
        fallback_url = f"https://github.com/{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}"
        project = await project_repo.get_or_create_by_github_url(
            name=f"{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}",
            github_url=fallback_url,
        )

    processor = SecurityProcessor(session_factory=AsyncSessionLocal)
    # processor.process_run resolves the project row itself and builds a
    # per-project GitHubClient when credentials are set (V2.8+).
    background_tasks.add_task(processor.process_run, project.id, body.run_id)

    return {"status": "accepted", "run_id": body.run_id, "project_id": project.id}


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

@router.get("/findings", response_model=list[FindingOut])
async def list_findings(
    response: Response,
    project_id: int | None = None,
    severity: str | None = None,
    tool: str | None = None,
    status: str | None = None,
    category: str | None = None,
    q: str | None = None,
    run_id: int | None = None,
    exclude_revoked: bool = False,
    skip: int = 0,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_read_access),
) -> list[Finding]:
    """List findings với filter mở rộng.

    Query params:
    - project_id: lọc theo project
    - severity: critical|high|medium|low|info
    - tool: semgrep|codeql|spotbugs|eslint|trivy|dependency-check|...
    - status: pending_review|ai_analyzed|APPROVED|REVOKED
    - category: sast | deps  (deps = trivy + dependency-check; sast = các tool còn lại)
    - q: search trong message / file_path / rule_id (LIKE %q%, case-insensitive)
    - skip / limit: pagination

    Response headers:
    - X-Total-Count: tổng số findings match filter (trước khi apply skip/limit)
    """
    repo = FindingRepository(session)
    # V3.3 — when RBAC on + non-admin, scope to user's memberships only.
    scope_ids = allowed_project_ids(user)
    if scope_ids is not None and project_id is not None and project_id not in scope_ids:
        raise HTTPException(
            status_code=403,
            detail=f"Project {project_id} not in your memberships",
        )
    filter_kwargs = dict(
        project_id=project_id,
        project_ids=scope_ids if project_id is None else None,
        severity=severity,
        tool=tool,
        status=status,
        category=category,
        q=q,
        run_id=run_id,
        exclude_revoked=exclude_revoked,
    )
    total = await repo.count_with_filters(**filter_kwargs)
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    return await repo.list_with_filters(skip=skip, limit=limit, **filter_kwargs)


@router.post("/findings/triage")
async def triage_findings(
    project_id: int | None = None,
    run_id: int | None = None,
    confidence_threshold: float = 0.8,
    dry_run: bool = False,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    current: User = Depends(get_current_user_required),
) -> dict:
    """V3.1 Tier 3 — batch AI triage. Sends pending findings (max `limit`) to
    Gemini for FP/TP classification; REVOKES findings classified FALSE_POSITIVE
    with confidence ≥ threshold unless `dry_run=true` (preview only).

    Scope by project_id and/or run_id. Requires security_lead+ on the project
    (or global admin) — AI-driven mass revoke is a privileged operation.
    """
    from ..repositories import ProjectMemberRepository, role_satisfies
    from ..services.llm.triage import TriageService

    if project_id is not None and current.role != "admin":
        member_role = await ProjectMemberRepository(session).get_role(
            project_id, current.username,
        )
        if member_role is None or not role_satisfies(member_role, "security_lead"):
            raise HTTPException(
                status_code=403,
                detail="security_lead role required for AI triage",
            )

    repo = FindingRepository(session)
    findings = await repo.list_with_filters(
        project_id=project_id,
        run_id=run_id,
        status="pending_review",
        skip=0,
        limit=limit,
    )

    if not findings:
        return {"total": 0, "auto_revoked": 0, "items": [], "dry_run": dry_run}

    svc = TriageService()
    return await svc.triage_findings(
        session, findings,
        confidence_threshold=confidence_threshold,
        dry_run=dry_run,
        invoked_by=f"ai-triage (by {current.username})",
    )


@router.get("/findings/gate-count")
async def findings_gate_count(
    project_id: int | None = None,
    run_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Severity counts excluding REVOKED — for the V3.1 Tier 4 Security Gate.

    A pipeline step in sast-action calls this with the current run's id and
    decides pass/fail based on the active (non-suppressed) finding counts.
    The point: once a developer has triaged false positives, the next run
    can pass without anyone touching code.

    V3.3 auth: accepts EITHER
      • a valid JWT (dashboard caller), OR
      • CI_WEBHOOK_TOKEN as a bearer (CI runner — same secret used for
        /webhook/pipeline-complete so callers don't manage two tokens), OR
      • anonymous when ANONYMOUS_READ_ENABLED=true (legacy bypass).
    """
    if not settings.ANONYMOUS_READ_ENABLED:
        token = credentials.credentials if credentials else None
        # CI fast path — token matches the webhook shared secret.
        if token and settings.CI_WEBHOOK_TOKEN and token == settings.CI_WEBHOOK_TOKEN:
            pass
        else:
            # Otherwise, demand a real JWT.
            await get_current_user(credentials)
    repo = FindingRepository(session)
    common = dict(project_id=project_id, run_id=run_id, exclude_revoked=True)
    critical = await repo.count_with_filters(severity="critical", **common)
    high = await repo.count_with_filters(severity="high", **common)
    medium = await repo.count_with_filters(severity="medium", **common)
    low = await repo.count_with_filters(severity="low", **common)
    return {
        "project_id": project_id,
        "run_id": run_id,
        "exclude_revoked": True,
        "critical": critical,
        "high": high,
        "medium": medium,
        "low": low,
    }


@router.get("/findings/{finding_id}", response_model=FindingOut)
async def get_finding(
    finding_id: int,
    session: AsyncSession = Depends(get_session),
    _: User | None = Depends(require_read_access),
) -> Finding:
    finding = await FindingRepository(session).get(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return finding


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


@router.get(
    "/github/runs/{run_id}/findings", response_model=list[FindingOut],
    dependencies=[Depends(require_read_access)],
)
async def get_run_findings(
    run_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[Finding]:
    """Return all findings from a specific GitHub Actions workflow run."""
    return await FindingRepository(session).list_for_run(run_id)

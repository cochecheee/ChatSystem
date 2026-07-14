from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import (
    User,
    get_current_user,
    require_read_access,
)
from ..core.auth import (
    security as _bearer_auth,
)
from ..core.config import settings
from ..core.db import get_session
from ..models.entities import Project
from ..models.schemas import (
    GatePolicyUpdate,
    IntegrationInfo,
    MonitorTargetUpdate,
    ProjectCreate,
    ProjectCreateOut,
    ProjectOut,
)
from ..repositories import ArtifactRepository, FindingRepository, ProjectRepository

router = APIRouter()

_bearer = HTTPBearer(auto_error=False)  # Authorization: Bearer <token>


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


async def _project_role(
    current: User,
    project_id: int,
    session: AsyncSession,
) -> str | None:
    """Resolve the caller's role on a project for the owner/admin gates.

    Trusts the JWT membership snapshot first, then falls back to a DB lookup
    when the snapshot is absent or doesn't include this project. Shared by the
    integration / rotate-token / gate-policy / monitor-target / archive / delete
    handlers so they all resolve the project role identically.
    """
    role = current.memberships.get(project_id) if current.memberships else None
    if role is None:
        from ..repositories import ProjectMemberRepository
        role = await ProjectMemberRepository(session).get_role(project_id, current.username)
    return role


class MemberUpsert(BaseModel):
    username: str
    role: str  # viewer | developer | security_lead | owner


class SuppressionCreate(BaseModel):
    reason: str
    rule_id: str | None = None
    file_glob: str | None = None
    tool: str | None = None
    severity_max: str | None = None
    expires_in_days: int | None = 90  # default 90d expiry — temp by design


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def _render_caller_workflow(project_id: int, language: str) -> str:
    """File `.github/workflows/security.yml` sẵn-để-commit cho repo mục tiêu:
    một caller gọi reusable workflow, đã điền `language` + `mcp_project_id` và
    nối 2 secret dashboard. Ngôn ngữ ghim về java|python|node|go."""
    lang = language if language in ("java", "python", "node", "go") else "python"
    return (
        "name: Security scan\n"
        "on:\n"
        "  push: { branches: [main, master] }\n"
        "  pull_request:\n"
        "  workflow_dispatch:\n"
        "permissions:\n"
        "  contents: read\n"
        "  security-events: write\n"
        "  actions: read\n"
        "  issues: write          # BẮT BUỘC: job DAST (OWASP ZAP) cần quyền này mới chạy\n"
        "jobs:\n"
        "  security:\n"
        "    uses: cochecheee/sast-action/.github/workflows/sast-ci.yml@master\n"
        "    with:\n"
        f"      language: {lang}\n"
        f"      mcp_project_id: {project_id}\n"
        "      gate_enabled: true\n"
        "    secrets:\n"
        "      dashboard_url:   ${{ secrets.MCP_GATEWAY_URL }}\n"
        "      dashboard_token: ${{ secrets.MCP_WEBHOOK_TOKEN }}\n"
        "      # nvd_api_key: OPTIONAL — chỉ dùng cho OWASP Dependency-Check (Java);\n"
        "      # bỏ trống vẫn quét được (SCA Java có thể chậm/bị NVD rate-limit).\n"
        "      nvd_api_key:     ${{ secrets.NVD_API_KEY }}\n"
    )


@router.post("/projects", response_model=ProjectCreateOut, status_code=201)
async def create_project(
    body: ProjectCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current: User = Depends(get_current_user_required),
) -> ProjectCreateOut:
    """Tạo project với full credentials (V2.8 P7) + trả về gói tích hợp one-time.

    V3.8 — yêu cầu xác thực: khi RBAC bật, người tạo trở thành `owner`.
    Secrets (`github_token`, `gemini_api_key`, `webhook_token`) được Fernet-encrypt
    khi `FERNET_KEY` set; `active=False` map sang INTEGER 0.

    V4.4 — endpoint tự sinh `webhook_token` per-project và trả về khối
    `integration` (project_id + token plaintext + gateway URL + secrets + file
    workflow điền sẵn). Token **chỉ xuất hiện Ở ĐÂY** (giống /webhook/rotate);
    các API khác chỉ thấy `has_webhook_token`. Muốn lấy lại phải rotate.
    """
    import secrets as _secrets

    repo = ProjectRepository(session)
    fields = body.model_dump(exclude_unset=False)
    # `language` chỉ để render snippet — KHÔNG phải cột Project → pop ra.
    language = str(fields.pop("language", "python") or "python")
    # Bool -> int để khớp Mapped[int] cột active
    fields["active"] = 1 if fields.get("active", True) else 0
    # V4.4 — sinh token per-project ngay khi tạo (Fernet-encrypt khi lưu).
    webhook_token = _secrets.token_urlsafe(32)
    fields["webhook_token"] = webhook_token
    project = await repo.create(**fields)
    # Creator becomes owner so per-project RBAC has an accountable owner.
    if settings.RBAC_PER_PROJECT:
        from ..repositories import ProjectMemberRepository
        await ProjectMemberRepository(session).upsert(
            project_id=project.id, username=current.username, role="owner",
        )

    # Base URL từ request (khớp local dev + tunnel/proxy) — như /integration.
    scheme = request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    base = f"{scheme}://{host}"

    out = ProjectCreateOut.model_validate(project)
    out.integration = IntegrationInfo(
        project_id=project.id,
        webhook_token=webhook_token,
        dashboard_url=base,
        secrets_to_set=[
            {"name": "MCP_GATEWAY_URL", "value": base, "required": "true",
             "note": "URL của MCP Gateway (dashboard) để CI gửi kết quả về."},
            {"name": "MCP_WEBHOOK_TOKEN", "value": webhook_token, "required": "true",
             "note": "Token xác thực CI → Gateway. Chỉ hiển thị 1 lần."},
            {"name": "NVD_API_KEY", "value": "", "required": "false",
             "note": ("OPTIONAL — chỉ cần cho OWASP Dependency-Check (dự án Java). "
                      "Xin miễn phí tại nvd.nist.gov/developers/request-an-api-key. "
                      "Bỏ trống vẫn quét được nhưng SCA Java có thể chậm/bị rate-limit.")},
        ],
        workflow_yaml=_render_caller_workflow(project.id, language),
        note=(
            "Token webhook chỉ hiển thị 1 LẦN — lưu ngay vào GitHub repo "
            "(Settings → Secrets → Actions). Muốn lấy lại phải Rotate webhook token."
        ),
    )
    return out


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
    current: User = Depends(get_current_user_optional),
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
    body: MemberUpsert,
    session: AsyncSession = Depends(get_session),
    current: User = Depends(get_current_user_required),
) -> dict:
    """Add or update a member. Caller must be project `owner` (or global admin)."""
    from ..repositories import ROLE_LATTICE, ProjectMemberRepository
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

    from ..repositories import ProjectMemberRepository, SuppressionRuleRepository, role_satisfies

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
        from datetime import UTC, datetime
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
    from ..repositories import ProjectMemberRepository, SuppressionRuleRepository, role_satisfies

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
    current: User = Depends(get_current_user_required),
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
    current: User = Depends(get_current_user_optional),
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
            # JWT carries a membership snapshot (V3.0); fall back to DB.
            can_reveal = await _project_role(current, project_id, session) == "owner"

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
    current: User = Depends(get_current_user_required),
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
        if await _project_role(current, project_id, session) != "owner":
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
    body: GatePolicyUpdate,
    session: AsyncSession = Depends(get_session),
    current: User = Depends(get_current_user_required),
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
        if await _project_role(current, project_id, session) != "owner":
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


@router.patch("/projects/{project_id}/monitor")
async def update_monitor_target(
    project_id: int,
    body: MonitorTargetUpdate,
    session: AsyncSession = Depends(get_session),
    current: User = Depends(get_current_user_required),
) -> dict:
    """V3.7 — set/clear a project's uptime Monitor staging URL.

    Owner / global admin only. The monitor loop auto-picks up active projects
    with a non-empty `staging_url` — so this single endpoint is all an
    inheritor project needs to opt into uptime monitoring (no server env).
    Pass empty string to stop monitoring the project.
    """
    from ..repositories.audit_log_repo import write_audit

    project = await ProjectRepository(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if current.role != "admin":
        if await _project_role(current, project_id, session) != "owner":
            raise HTTPException(
                status_code=403,
                detail="Only project owner (or global admin) can change the monitor target",
            )

    url = (body.staging_url or "").strip()
    if url and not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="staging_url must start with http:// or https://")

    old = project.staging_url
    await ProjectRepository(session).update(project, {"staging_url": url})
    await write_audit(
        session, actor=current.username, action="set_monitor_target",
        project_id=project_id, target_kind="project", target_id=project_id,
        payload={"old": old, "new": url},
    )
    await session.commit()
    return {"project_id": project_id, "staging_url": url, "monitored": bool(url)}


@router.post("/projects/{project_id}/archive", status_code=200)
async def archive_project(
    project_id: int,
    session: AsyncSession = Depends(get_session),
    current: User = Depends(get_current_user_required),
) -> dict:
    """V3.6 — soft delete. Sets archived_at; project hidden from default lists
    but findings/runs preserved. Owner / admin only. Reverse via /unarchive.
    """
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    from ..repositories.audit_log_repo import write_audit

    project = await ProjectRepository(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if current.role != "admin":
        if await _project_role(current, project_id, session) != "owner":
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
    current: User = Depends(get_current_user_required),
) -> Response:
    """Xoá project + cascade toàn bộ dữ liệu con.

    Hard delete. Xoá theo thứ tự FK-safe MỌI bảng tham chiếu projects.id
    (findings -> artifacts -> pipeline_runs -> webhook_deliveries ->
    suppression_rules -> project_members -> uptime_checks -> alerts) trước
    khi xoá project. `audit_log` dùng ON DELETE SET NULL nên DB tự xử lý
    (giữ lại log lịch sử).

    V3.8 — yêu cầu `owner` của project hoặc global `admin` (giống endpoint
    archive). Trước đây handler KHÔNG gate auth → bất kỳ ai cũng xoá sạch
    project + toàn bộ dữ liệu con. Flow "remove" thông thường vẫn nên dùng
    POST .../archive (V3.6 soft delete) để giữ dữ liệu cho trend/audit.
    """
    from sqlalchemy import delete as _delete
    from sqlalchemy import or_ as _or
    from sqlalchemy import select as _select

    from ..models.entities import (
        Alert,
        CommandFeedback,
        Finding,
        FindingAction,
        PipelineRun,
        ProjectMember,
        SuppressionRule,
        UptimeCheck,
        WebhookDelivery,
    )

    project_repo = ProjectRepository(session)
    artifact_repo = ArtifactRepository(session)
    finding_repo = FindingRepository(session)

    project = await project_repo.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # Authorization: global admin OR project owner (same as archive).
    if current.role != "admin":
        if await _project_role(current, project_id, session) != "owner":
            raise HTTPException(status_code=403, detail="Only owner/admin may delete a project")

    artifacts = await artifact_repo.list_for_project(project_id)
    artifact_ids = [a.id for a in artifacts]
    # Con trước, cha sau — tránh vi phạm khoá ngoại trên InnoDB.
    # finding_actions.finding_id VÀ command_feedback.finding_id đều là FK non-cascade
    # -> findings.id (nullable): phải xoá TRƯỚC findings, nếu không MySQL 1451 khi
    # project có finding đã /approve|/revoke (action row) hoặc /feedback (feedback row).
    finding_ids_subq = _select(Finding.id).where(
        _or(
            Finding.project_id == project_id,
            Finding.artifact_id.in_(artifact_ids),
        ),
    )
    await session.execute(
        _delete(FindingAction).where(FindingAction.finding_id.in_(finding_ids_subq)),
    )
    await session.execute(
        _delete(CommandFeedback).where(CommandFeedback.finding_id.in_(finding_ids_subq)),
    )
    await finding_repo.delete_by_artifact_ids(artifact_ids)
    await artifact_repo.delete_by_ids(artifact_ids)
    for _model in (
        PipelineRun,
        WebhookDelivery,
        SuppressionRule,
        ProjectMember,
        UptimeCheck,
        Alert,
    ):
        await session.execute(
            _delete(_model).where(_model.project_id == project_id),
        )
    await project_repo.delete(project)  # commit cuối -> 1 transaction
    return Response(status_code=204)

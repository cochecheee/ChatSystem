from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import User, create_access_token, get_current_user
from ..core.db import get_session
from ..models.schemas import (
    CommandRequest,
    CommandResponse,
    TokenRequest,
    TokenResponse,
)
from ..repositories import FindingRepository, ProjectMemberRepository, UserRepository
from ..services import report_service
from ..services.command_service import CommandService
from ..services.llm.client import GeminiClient

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

COMMAND_ROLES: dict[str, list[str]] = {
    "explain":  ["developer", "security_lead", "admin"],
    "fix":      ["developer", "security_lead", "admin"],
    "report":   ["developer", "security_lead", "admin"],
    "scan":     ["security_lead", "admin"],
    "rerun":    ["security_lead", "admin"],
    "approve":  ["security_lead", "admin"],
    "revoke":   ["security_lead", "admin"],
    "unrevoke": ["security_lead", "admin"],
    # Báo cáo tiến độ docx ch.4.3 — 4 lệnh còn lại
    "status":   ["developer", "security_lead", "admin"],
    "results":  ["developer", "security_lead", "admin"],
    "help":     ["developer", "security_lead", "admin"],
    "feedback": ["developer", "security_lead", "admin"],
}

_command_service = CommandService()


@router.post("/command", response_model=CommandResponse)
async def handle_command(
    request: CommandRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> CommandResponse:
    cmd = request.command.lstrip("/").lower()

    allowed_roles = COMMAND_ROLES.get(cmd)
    if allowed_roles is None:
        raise HTTPException(status_code=400, detail=f"Lệnh không hợp lệ: /{cmd}")

    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"/{cmd} yêu cầu role: {allowed_roles}. Bạn đang là: {current_user.role}",
        )

    return await _command_service.handle(cmd, request, current_user, db)


@router.get("/report")
async def download_report(
    project_id: int | None = None,
    severity: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    if current_user.role not in COMMAND_ROLES["report"]:
        raise HTTPException(status_code=403, detail="Không đủ quyền truy cập báo cáo.")

    # V3.5 RBAC audit — previously this endpoint trusted role-only, so a
    # developer with access to project A could download report for project
    # B by passing ?project_id=B. Now we enforce per-project membership
    # before generating the HTML.
    from ..core.auth import allowed_project_ids
    scope = allowed_project_ids(current_user)
    if scope is not None and project_id is not None and project_id not in scope:
        raise HTTPException(
            status_code=403,
            detail=f"Project {project_id} not in your memberships",
        )

    # V3.8 — report phản ánh current-state (run mới nhất mỗi project) để khớp
    # với dashboard, không cộng dồn findings của các lần CI chạy lại.
    html_content = await report_service.generate_html(
        db,
        project_id=project_id,
        severity=severity,
        latest_run_only=True,
    )
    return Response(
        content=html_content,
        media_type="text/html",
        headers={"Content-Disposition": "attachment; filename=security-report.html"},
    )


# ---------------------------------------------------------------------------
# Auth — demo token endpoint (thesis/dev mode)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Free-form chat (Gemini)
# ---------------------------------------------------------------------------

class ChatMessageRequest(BaseModel):
    text: str
    finding_id: int | None = None  # optional context: which finding the user is asking about


class ChatMessageResponse(BaseModel):
    reply: str
    suggested_command: str | None = None  # e.g. "/explain 5" — frontend can show as a one-click chip


_gemini: GeminiClient | None = None


def _get_gemini() -> GeminiClient:
    global _gemini
    if _gemini is None:
        _gemini = GeminiClient()
    return _gemini


def _suggested_command(text: str) -> str | None:
    """Heuristic: map common natural-language phrases to a slash command.

    Lets the user say "phân tích finding 5" and get a clickable /explain 5
    suggestion in the AI reply, without forcing them to learn the syntax.
    """
    import re
    t = text.lower()

    m = re.search(r"(?:explain|phân tích|giải thích).*?\b(\d+)\b", t)
    if m:
        return f"/explain {m.group(1)}"
    m = re.search(r"(?:fix|sửa|khắc phục).*?\b(\d+)\b", t)
    if m:
        return f"/fix {m.group(1)}"
    m = re.search(r"(?:approve|phê duyệt|duyệt).*?\b(\d+)\b", t)
    if m:
        return f"/approve {m.group(1)}"
    # unrevoke must be checked BEFORE revoke — "unrevoke"/"khôi phục" else the
    # revoke pattern (substring "revoke") would swallow it.
    m = re.search(r"(?:unrevoke|khôi phục|bỏ thu hồi|huỷ thu hồi).*?\b(\d+)\b", t)
    if m:
        return f"/unrevoke {m.group(1)}"
    m = re.search(r"(?:revoke|thu hồi|huỷ duyệt).*?\b(\d+)\b", t)
    if m:
        return f"/revoke {m.group(1)}"
    if any(k in t for k in ["scan mới", "kích hoạt scan", "chạy scan", "trigger scan"]):
        return "/scan"
    if any(k in t for k in ["báo cáo", "report", "xuất file"]):
        return "/report"
    return None


async def _build_context(db: AsyncSession, finding_id: int | None) -> str:
    parts: list[str] = []
    repo = FindingRepository(db)

    if finding_id is not None:
        f = await repo.get(finding_id)
        if f:
            parts.append(
                f"Finding hiện tại: #{f.id} | tool={f.tool} | rule={f.rule_id} | "
                f"severity={f.severity} | file={f.file_path}:{f.line_number or '?'}\n"
                f"Mô tả: {f.message[:300]}"
            )

    # Top recent critical/high findings (no JWT info; just stats)
    recent = await repo.list_recent_critical(limit=5)
    if recent:
        lines = [
            f"  - #{f.id} [{f.severity}] {f.tool}/{f.rule_id} ({f.file_path})"
            for f in recent
        ]
        parts.append("Findings nghiêm trọng gần nhất:\n" + "\n".join(lines))

    return "\n\n".join(parts)


@router.post("/message", response_model=ChatMessageResponse)
async def chat_message(
    request: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> ChatMessageResponse:
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Tin nhắn không được để trống.")

    suggested = _suggested_command(text)

    try:
        context = await _build_context(db, request.finding_id)
        reply = await _get_gemini().chat(text, context=context)
    except Exception as exc:
        log.warning("Gemini chat failed: %s", exc)
        if suggested:
            reply = f"Tôi nghĩ bạn muốn chạy lệnh `{suggested}`. Nhấn vào gợi ý bên dưới để thực thi."
        else:
            reply = (
                "Hiện không thể kết nối tới AI. Bạn có thể dùng các lệnh nhanh: "
                "/explain [id], /fix [id], /scan, /report."
            )

    return ChatMessageResponse(reply=reply, suggested_command=suggested)


class AuthMeResponse(BaseModel):
    username: str
    role: str


@router.get("/auth/me", response_model=AuthMeResponse, tags=["auth"])
async def auth_me(current_user: User = Depends(get_current_user)) -> AuthMeResponse:
    """Validate JWT và trả về user info. Frontend dùng sau reload để check token còn valid."""
    return AuthMeResponse(username=current_user.username, role=current_user.role)


@router.post("/auth/token", response_model=TokenResponse, tags=["auth"])
async def login(
    request: TokenRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """V3.8 — password login.

    Verifies a bcrypt password against the `users` table and issues a JWT.
    The global `role` claim is read from the user row (NOT from the request),
    so it can no longer be self-selected/forged. Any `role` sent in the body
    is ignored.

    Seeded users (cochecheee + each project member) get the default password
    on first boot (settings.DEFAULT_USER_PASSWORD); rotate via a future
    change-password flow. Bad username or password → 401 (indistinguishable
    to avoid leaking which usernames exist).

    V3.0: JWT also carries a per-project memberships snapshot so
    `require_project_access` can check without hitting the DB each request.
    """
    user = await UserRepository(session).verify_credentials(
        request.username, request.password,
    )
    if user is None:
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu")

    memberships = await ProjectMemberRepository(session).memberships_dict(user.username)
    token = create_access_token(
        username=user.username, role=user.role, memberships=memberships,
    )
    return TokenResponse(access_token=token)

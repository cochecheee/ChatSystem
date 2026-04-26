from __future__ import annotations

import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import User, create_access_token, get_current_user
from ..core.db import get_session
from ..models.schemas import (
    CommandRequest,
    CommandResponse,
    TokenRequest,
    TokenResponse,
)
from ..services.command_service import CommandService
from ..services import report_service

router = APIRouter(prefix="/api/chat", tags=["chat"])

COMMAND_ROLES: dict[str, list[str]] = {
    "explain": ["developer", "security_lead", "admin"],
    "fix":     ["developer", "security_lead", "admin"],
    "report":  ["developer", "security_lead", "admin"],
    "scan":    ["security_lead", "admin"],
    "rerun":   ["security_lead", "admin"],
    "approve": ["security_lead", "admin"],
    "revoke":  ["security_lead", "admin"],
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    if current_user.role not in COMMAND_ROLES["report"]:
        raise HTTPException(status_code=403, detail="Không đủ quyền truy cập báo cáo.")
    html_content = await report_service.generate_html(db)
    return Response(
        content=html_content,
        media_type="text/html",
        headers={"Content-Disposition": "attachment; filename=security-report.html"},
    )


# ---------------------------------------------------------------------------
# Auth — demo token endpoint (thesis/dev mode)
# ---------------------------------------------------------------------------

@router.post("/auth/token", response_model=TokenResponse, tags=["auth"])
async def demo_login(request: TokenRequest) -> TokenResponse:
    """Demo login — trả về JWT không cần password (dành cho thesis demo).

    Trong production, thay bằng auth thật (LDAP, OAuth2, v.v.)
    """
    valid_roles = {"developer", "security_lead", "admin"}
    if request.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Role không hợp lệ. Chọn: {valid_roles}")

    token = create_access_token(username=request.username, role=request.role)
    return TokenResponse(access_token=token)

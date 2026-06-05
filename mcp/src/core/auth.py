from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session

security = HTTPBearer(auto_error=False)


class User(BaseModel):
    username: str
    role: str  # "developer" | "security_lead" | "admin"
    # V3.0: { project_id: role } snapshot from issue time. None means the
    # token predates V3.0 and the dep should re-fetch from DB.
    memberships: dict[int, str] | None = None


def create_access_token(
    username: str,
    role: str,
    memberships: dict[int, str] | None = None,
) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict = {"sub": username, "role": role, "exp": expire}
    if memberships is not None:
        # JSON cannot key int — stringify project ids.
        payload["memberships"] = {str(k): v for k, v in memberships.items()}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, settings.SECRET_KEY, algorithms=["HS256"])
        username: str | None = payload.get("sub")
        role: str | None = payload.get("role")
        if not username or not role:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        raw_m = payload.get("memberships")
        memberships: dict[int, str] | None = None
        if isinstance(raw_m, dict):
            memberships = {int(k): v for k, v in raw_m.items()}
        return User(username=username, role=role, memberships=memberships)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def allowed_project_ids(user: User | None) -> list[int] | None:
    """V3.3 — return the set of project ids the caller may read, or None for
    'no restriction' (admin, anonymous bypass, or RBAC off).

    Callers fold this into their filter clauses; a caller that gets a non-None
    list MUST scope results to those ids only. Returning an empty list means
    "user is authenticated but has zero memberships" — the route should then
    return an empty result, not unfiltered data.
    """
    if not settings.RBAC_PER_PROJECT:
        return None
    if user is None or user.role == "admin":
        return None
    if user.memberships is None:
        return []  # JWT without memberships claim → conservative empty scope
    return list(user.memberships.keys())


async def require_read_access(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User | None:
    """V3.3 — Gate read endpoints with a kill-switch.

    When `ANONYMOUS_READ_ENABLED=true` (legacy V2.x bypass) → return None
    without checking the token, so callers can stay anonymous.

    When `ANONYMOUS_READ_ENABLED=false` (default, secure) → behave like
    `get_current_user`: require a valid JWT, return the User. Callers that
    need the User object (for membership filtering) can use the return
    value; callers that just need a gate can ignore it.
    """
    if settings.ANONYMOUS_READ_ENABLED:
        return None
    return await get_current_user(credentials)


# V3.0 — per-project access dependency factory.
#
# Usage in a route:
#     @router.post("/findings/{fid}/approve",
#                  dependencies=[Depends(require_project_access(min_role="security_lead"))])
#
# When `RBAC_PER_PROJECT=false`, behaves like get_current_user (no-op gate).
# `project_id` is resolved from path/query param of the same name on the
# request; if absent, the check is skipped (route-level current_user still
# needed). Global role `admin` always bypasses.


def require_project_access(min_role: str = "viewer"):
    """Return a FastAPI dependency that enforces per-project role >= min_role.

    Resolves project_id from request.path_params first, then query params.
    Routes without a project_id in either place fall back to the global
    role check (legacy V2.x behavior). Returns the authenticated User on
    success so the caller can read .username for audit logs.
    """
    from fastapi import Request

    from ..repositories import ProjectMemberRepository, role_satisfies

    async def _dep(
        request: Request,
        current: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> User:
        # Kill-switch: flag off → behave like a plain auth check.
        if not settings.RBAC_PER_PROJECT:
            return current

        # Admin global role bypasses every per-project gate. Operator
        # override for demo / incident response.
        if current.role == "admin":
            return current

        raw_pid = (
            request.path_params.get("project_id")
            or request.query_params.get("project_id")
        )
        if raw_pid is None:
            # No project scope on this route → can't gate; fall back to auth.
            return current
        try:
            project_id = int(raw_pid)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid project_id")

        # Trust JWT membership snapshot if present; else hit DB.
        actual_role: str | None
        if current.memberships is not None:
            actual_role = current.memberships.get(project_id)
        else:
            repo = ProjectMemberRepository(session)
            actual_role = await repo.get_role(project_id, current.username)

        if actual_role is None or not role_satisfies(actual_role, min_role):
            raise HTTPException(
                status_code=403,
                detail=f"User '{current.username}' lacks '{min_role}' on project {project_id}",
            )
        return current

    return _dep


async def enforce_finding_project_access(
    finding_id: int,
    user: User,
    session: AsyncSession,
    *,
    min_role: str = "developer",
) -> None:
    """V3.0 RBAC for finding-scoped actions (approve/revoke/explain).

    The `require_project_access` dep can only resolve project_id from path/query
    params, but findings are addressed by finding_id and we have to traverse
    Finding -> Artifact -> Project to find the project. This helper does that
    lookup + role check inline so each finding-action endpoint can call it.

    Kill-switch: settings.RBAC_PER_PROJECT=false → no-op.
    Global admin always bypasses.
    """
    if not settings.RBAC_PER_PROJECT:
        return
    if user.role == "admin":
        return

    from ..models.entities import Artifact, Finding
    from ..repositories import ProjectMemberRepository, role_satisfies

    finding = await session.get(Finding, finding_id)
    if finding is None:
        return  # caller will 404 separately; we just don't gate non-existent rows
    artifact = await session.get(Artifact, finding.artifact_id)
    if artifact is None:
        return
    project_id = artifact.project_id

    actual_role: str | None
    if user.memberships is not None:
        actual_role = user.memberships.get(project_id)
    else:
        actual_role = await ProjectMemberRepository(session).get_role(
            project_id, user.username,
        )

    if actual_role is None or not role_satisfies(actual_role, min_role):
        raise HTTPException(
            status_code=403,
            detail=(
                f"User '{user.username}' lacks '{min_role}' on project {project_id} "
                f"(finding {finding_id} belongs to that project)"
            ),
        )


async def enforce_run_project_access(
    run_id: int,
    user: User | None,
    session: AsyncSession,
    *,
    min_role: str = "viewer",
) -> None:
    """V3.7 RBAC for run-scoped endpoints (run findings/artifacts/reprocess).

    A GitHub workflow run maps 1:1 to a project; we resolve it via the run's
    Artifact rows (Artifact.github_run_id) and check the caller's membership.

    Kill-switch: RBAC_PER_PROJECT=false → no-op. Global admin and the
    anonymous-read bypass (user is None) → no-op. A run with no ingested
    artifacts yet (unknown project) is not gated here — the underlying query
    returns an empty/GitHub-sourced result, and reprocess falls back to the
    env project which only an authenticated caller can reach.
    """
    if not settings.RBAC_PER_PROJECT:
        return
    if user is None or user.role == "admin":
        return

    from sqlalchemy import select

    from ..models.entities import Artifact
    from ..repositories import ProjectMemberRepository, role_satisfies

    rows = await session.execute(
        select(Artifact.project_id)
        .where(Artifact.github_run_id == run_id)
        .distinct()
    )
    project_ids = [r[0] for r in rows.all() if r[0] is not None]
    if not project_ids:
        return  # run not ingested → nothing to scope against

    for pid in project_ids:
        if user.memberships is not None:
            role = user.memberships.get(pid)
        else:
            role = await ProjectMemberRepository(session).get_role(pid, user.username)
        if role is not None and role_satisfies(role, min_role):
            return

    raise HTTPException(
        status_code=403,
        detail=f"Run {run_id} belongs to a project not in your memberships",
    )

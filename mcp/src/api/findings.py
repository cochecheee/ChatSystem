"""Findings-scoped endpoints.

Extracted from `api/artifacts.py` in the Phase 1 split so the file owning
project/webhook/ingest concerns isn't tangled with finding queries. Six
endpoints live here:

  GET    /findings                            list with filters
  GET    /findings/ai-summary                 Gemini risk briefing
  POST   /findings/triage                     batch FP triage
  GET    /findings/gate-count                 CI gate decision input
  GET    /findings/{finding_id}               one row
  GET    /github/runs/{run_id}/findings       all findings of one run

The router is mounted into the app from main.py alongside artifacts_router.
External imports of `src.api.artifacts.settings` etc. still work because
artifacts.py keeps those symbols.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import (
    User,
    allowed_project_ids,
    get_current_user,
    get_current_user as get_current_user_required,
    require_read_access,
)
from ..core.config import settings
from ..core.db import get_session
from ..models.entities import Finding
from ..models.schemas import FindingOut
from ..repositories import FindingRepository

router = APIRouter()

_bearer = HTTPBearer(auto_error=False)


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


@router.get("/findings/ai-summary")
async def findings_ai_summary(
    project_id: int | None = None,
    run_id: int | None = None,
    force_refresh: bool = False,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_read_access),
) -> dict:
    """V3.3 Part B — Gemini-generated risk briefing for the Overview card.

    Returns a structured response (overview / top_risks / recommendations /
    pipeline_health) so the FE can render a multi-section card instead of
    a paragraph blob. Cached in-memory by (project_id, run_id) for 10
    minutes; pass `force_refresh=true` to bust the cache.

    Authorization: same as other reads. If project_id is given, caller must
    have membership when RBAC is on.
    """
    from ..services.llm.summary import SummaryService

    scope_ids = allowed_project_ids(user)
    if scope_ids is not None and project_id is not None and project_id not in scope_ids:
        raise HTTPException(
            status_code=403,
            detail=f"Project {project_id} not in your memberships",
        )

    svc = SummaryService()
    result = await svc.generate(
        session,
        project_id=project_id,
        run_id=run_id,
        force_refresh=force_refresh,
    )
    return result.model_dump()


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
    (or global admin).
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
    decides pass/fail based on the active (non-suppressed) counts. The point:
    once a developer has triaged false positives, the next run can pass
    without anyone touching code.

    Auth: accepts EITHER a valid JWT (dashboard) OR CI_WEBHOOK_TOKEN as a
    bearer (CI runner — same secret used for /webhook/pipeline-complete so
    callers don't manage two tokens) OR anonymous when ANONYMOUS_READ_ENABLED.
    """
    if not settings.ANONYMOUS_READ_ENABLED:
        token = credentials.credentials if credentials else None
        if token and settings.CI_WEBHOOK_TOKEN and token == settings.CI_WEBHOOK_TOKEN:
            pass
        else:
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
    user: User | None = Depends(require_read_access),
) -> Finding:
    finding = await FindingRepository(session).get(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")

    # V3.5 RBAC audit — finding -> artifact -> project chain check. Previously
    # /findings list filtered by membership but /findings/{id} GET did not,
    # so a developer could enumerate finding ids across other projects.
    scope = allowed_project_ids(user)
    if scope is not None:
        from ..models.entities import Artifact
        art = await session.get(Artifact, finding.artifact_id)
        if art is not None and art.project_id not in scope:
            raise HTTPException(
                status_code=403,
                detail=f"Finding {finding_id} belongs to a project not in your memberships",
            )
    return finding


@router.get(
    "/github/runs/{run_id}/findings",
    response_model=list[FindingOut],
    dependencies=[Depends(require_read_access)],
)
async def get_run_findings(
    run_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[Finding]:
    """Return all findings from a specific GitHub Actions workflow run."""
    return await FindingRepository(session).list_for_run(run_id)

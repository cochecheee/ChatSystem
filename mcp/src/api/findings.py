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
    enforce_run_project_access,
    ensure_project_in_scope,
    get_current_user,
    require_read_access,
)
from ..core.auth import (
    get_current_user as get_current_user_required,
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
    latest_run_only: bool = False,
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
    ensure_project_in_scope(user, project_id)
    scope_ids = allowed_project_ids(user)
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
        latest_run_only=latest_run_only,
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

    ensure_project_in_scope(user, project_id)

    svc = SummaryService()
    # V3.7 — khi không chỉ định project_id, scope briefing theo membership
    # (non-admin) để không lộ số liệu tổng hợp của project khác.
    summary_scope = allowed_project_ids(user) if project_id is None else None
    result = await svc.generate(
        session,
        project_id=project_id,
        run_id=run_id,
        force_refresh=force_refresh,
        project_ids=summary_scope,
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
    """V3.6 — Security Gate decision endpoint.

    The CI gate (sast-action's `security-gate` composite) calls this with
    the current project_id + run_id to get a pass/fail verdict. Two modes:

      - **With project_id** (recommended): server reads the project's
        gate_critical_threshold + gate_high_threshold from DB and decides
        pass/fail. Returns counts + thresholds + `pass: bool`. Lets owners
        adjust policy via dashboard without editing CI YAML.
      - **Without project_id** (legacy): server returns counts only.
        Caller still applies workflow-input thresholds (V3.1 behavior).

    Auth (V3.6):
      • JWT (dashboard caller)
      • Per-project webhook token via `Authorization: Bearer <token>`
        — matches Project.webhook_token (preferred over global)
      • Legacy global CI_WEBHOOK_TOKEN (kept for back-compat)
      • Anonymous when ANONYMOUS_READ_ENABLED=true (legacy bypass)
    """
    from ..repositories import ProjectRepository

    # --- Auth ---
    if not settings.ANONYMOUS_READ_ENABLED:
        token = credentials.credentials if credentials else None
        authed = False
        if token and settings.CI_WEBHOOK_TOKEN and token == settings.CI_WEBHOOK_TOKEN:
            authed = True   # legacy global webhook token
        elif token:
            # V3.5 per-project webhook tokens — anyone holding one of these
            # can ask the gate question (CI runner doesn't have a JWT). Still
            # constant-time compared inside the repo helper.
            proj = await ProjectRepository(session).find_by_webhook_token(token)
            if proj is not None:
                authed = True
        if not authed:
            await get_current_user(credentials)

    repo = FindingRepository(session)
    # §4.2.3 — gate counts ACTIVE risk only: exclude REVOKED (false-positive)
    # AND APPROVED (accepted-risk, audited). So an /approve on a critical lets
    # the PR merge on the next run, exactly like /revoke — both are recorded in
    # the audit trail, neither blocks the gate.
    common = dict(
        project_id=project_id, run_id=run_id,
        exclude_revoked=True, exclude_approved=True,
    )
    critical = await repo.count_with_filters(severity="critical", **common)
    high = await repo.count_with_filters(severity="high", **common)
    medium = await repo.count_with_filters(severity="medium", **common)
    low = await repo.count_with_filters(severity="low", **common)

    # V3.7 — ingest signal for the CI gate. The gate calls this with the
    # CURRENT run_id, but chat-system ingests the run asynchronously (webhook
    # → background process_run). If the gate reads counts BEFORE ingest it sees
    # 0/0 and would PASS for the wrong reason. `run_total` counts every finding
    # of the run (REVOKED included); `run_ingested` lets the gate poll until the
    # run is actually in the DB, then trust the REVOKED-excluded counts above.
    run_total = await repo.count_with_filters(project_id=project_id, run_id=run_id)
    run_ingested = run_total > 0

    # V3.6 — server-side policy decision when project_id is known.
    pass_verdict: bool | None = None
    policy: dict | None = None
    blocking: list[str] = []
    if project_id is not None:
        proj = await ProjectRepository(session).get(project_id)
        if proj is not None:
            crit_thr = proj.gate_critical_threshold
            high_thr = proj.gate_high_threshold
            policy = {"critical_threshold": crit_thr, "high_threshold": high_thr}
            if crit_thr > 0 and critical >= crit_thr:
                blocking.append(
                    f"critical findings {critical} >= threshold {crit_thr}"
                )
            if high_thr > 0 and high >= high_thr:
                blocking.append(
                    f"high findings {high} >= threshold {high_thr}"
                )
            pass_verdict = len(blocking) == 0

    return {
        "project_id": project_id,
        "run_id": run_id,
        "exclude_revoked": True,
        "exclude_approved": True,
        "critical": critical,
        "high": high,
        "medium": medium,
        "low": low,
        # V3.7 — ingest signal (see above). Gate polls on run_ingested.
        "run_total": run_total,
        "run_ingested": run_ingested,
        # V3.6 additions — None when project_id missing (back-compat shape).
        "policy": policy,
        "pass": pass_verdict,
        "blocking_reasons": blocking,
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
)
async def get_run_findings(
    run_id: int,
    exclude_revoked: bool = False,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_read_access),
) -> list[Finding]:
    """Return findings from a specific GitHub Actions workflow run.

    V3.7 — scoped by membership: a run's findings belong to one project, so
    a non-admin caller must be a member of that project (when RBAC is on).

    `exclude_revoked=true` hides REVOKED false-positives so the dashboard's
    latest-scan views don't resurface findings the team already triaged on a
    previous run (Tier-1 auto-revoke re-marks them REVOKED on every re-scan).
    """
    await enforce_run_project_access(run_id, user, session)
    return await FindingRepository(session).list_for_run(
        run_id, exclude_revoked=exclude_revoked,
    )

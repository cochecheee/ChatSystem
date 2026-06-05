from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import (
    User,
    allowed_project_ids,
    enforce_run_project_access,
    require_read_access,
)
from ..core.config import settings
from ..core.db import AsyncSessionLocal, get_session
from ..models.entities import WebhookDelivery
from ..models.schemas import ProcessRequest, ProcessResponse
from ..repositories import ArtifactRepository, FindingRepository, ProjectRepository
from ..services.github_client import GitHubClient
from ..services.processor import SecurityProcessor

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
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_read_access),
) -> list[dict]:
    """Return artifacts for the given workflow run.
    Use the `id` field as `github_artifact_id` in **POST /artifacts/process**.

    V3.7 — when the run is already ingested, scope by membership so a
    non-admin can't list another project's run artifacts.
    """
    await enforce_run_project_access(run_id, user, session)
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
        record_delivery,
        verify_signature_against_any_project,
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
# Reprocess — wipe a run's findings/artifacts and re-fetch from GitHub
# ---------------------------------------------------------------------------

@router.post("/github/runs/{run_id}/reprocess", status_code=202)
async def reprocess_run(
    run_id: int,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(require_read_access),
) -> dict:
    """Wipe existing findings/artifacts for a run and reprocess from GitHub.

    Used after fixing the normalizer or pulling in new artifact types — the
    previous artifacts in the DB are stale, so we delete them and re-fetch.

    V3.7 — destructive re-ingest: requires developer+ membership on the run's
    project (when RBAC is on). Admin bypasses; anonymous-read bypass still
    gated by the kill-switch via require_read_access.
    """
    await enforce_run_project_access(run_id, user, session, min_role="developer")
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

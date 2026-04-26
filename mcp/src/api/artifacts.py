from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy import select
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
# Projects
# ---------------------------------------------------------------------------

@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(
    body: ProjectCreate,
    session: AsyncSession = Depends(get_session),
) -> Project:
    project = Project(name=body.name, github_url=body.github_url)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(session: AsyncSession = Depends(get_session)) -> list[Project]:
    result = await session.execute(select(Project))
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# GitHub browser — inspect runs & artifacts without leaving Swagger UI
# ---------------------------------------------------------------------------

@router.get("/github/runs", summary="List recent workflow runs from GitHub")
async def list_github_runs(
    branch: str = "main",
    status: str = "completed",
    github: GitHubClient = Depends(get_github_client),
) -> list[dict]:
    """Return recent workflow runs for the configured repo.
    Use the `id` field as input for **GET /github/runs/{run_id}/artifacts**.
    """
    try:
        return await github.list_workflow_runs(
            workflow_name=settings.POLLING_WORKFLOW_NAME,
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
    project = await session.get(Project, body.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    artifact = Artifact(
        github_artifact_id=str(body.github_artifact_id),
        project_id=body.project_id,
        status="pending",
    )
    session.add(artifact)
    await session.commit()
    await session.refresh(artifact)

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

    CI_WEBHOOK_TOKEN trống → auth disabled (dev mode).
    """
    webhook_token = credentials.credentials if credentials else None
    if settings.CI_WEBHOOK_TOKEN and webhook_token != settings.CI_WEBHOOK_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid or missing webhook token")

    github_url = f"https://github.com/{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}"
    result = await session.execute(select(Project).where(Project.github_url == github_url))
    project = result.scalar_one_or_none()
    if project is None:
        project = Project(
            name=f"{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}",
            github_url=github_url,
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)

    processor = SecurityProcessor(session_factory=AsyncSessionLocal)
    background_tasks.add_task(processor.process_run, project.id, body.run_id)

    return {"status": "accepted", "run_id": body.run_id, "project_id": project.id}


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

@router.get("/findings", response_model=list[FindingOut])
async def list_findings(
    project_id: int | None = None,
    severity: str | None = None,
    skip: int = 0,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[Finding]:
    query = select(Finding).join(Artifact)
    if project_id is not None:
        query = query.where(Artifact.project_id == project_id)
    if severity is not None:
        query = query.where(Finding.severity == severity)
    query = query.order_by(Finding.id.desc()).offset(skip).limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/findings/{finding_id}", response_model=FindingOut)
async def get_finding(
    finding_id: int,
    session: AsyncSession = Depends(get_session),
) -> Finding:
    finding = await session.get(Finding, finding_id)
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
    artifact_result = await session.execute(
        select(Artifact).where(Artifact.github_run_id == run_id)
    )
    artifacts = list(artifact_result.scalars().all())
    project_id: int | None = None
    if artifacts:
        project_id = artifacts[0].project_id
        artifact_ids = [a.id for a in artifacts]
        from sqlalchemy import delete
        await session.execute(delete(Finding).where(Finding.artifact_id.in_(artifact_ids)))
        await session.execute(delete(Artifact).where(Artifact.id.in_(artifact_ids)))
        await session.commit()

    if project_id is None:
        github_url = f"https://github.com/{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}"
        result = await session.execute(select(Project).where(Project.github_url == github_url))
        project = result.scalar_one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy project gắn với run này.")
        project_id = project.id

    processor = SecurityProcessor(session_factory=AsyncSessionLocal)
    background_tasks.add_task(processor.process_run, project_id, run_id)
    return {"status": "accepted", "run_id": run_id, "deleted_artifacts": len(artifacts)}


@router.get("/github/runs/{run_id}/findings", response_model=list[FindingOut])
async def get_run_findings(
    run_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[Finding]:
    """Return all findings from a specific GitHub Actions workflow run."""
    artifact_result = await session.execute(
        select(Artifact).where(Artifact.github_run_id == run_id)
    )
    artifacts = artifact_result.scalars().all()
    if not artifacts:
        return []
    artifact_ids = [a.id for a in artifacts]
    finding_result = await session.execute(
        select(Finding)
        .where(Finding.artifact_id.in_(artifact_ids))
        .order_by(Finding.severity, Finding.rule_id)
    )
    return list(finding_result.scalars().all())

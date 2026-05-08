from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
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
# Projects
# ---------------------------------------------------------------------------

@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(
    body: ProjectCreate,
    session: AsyncSession = Depends(get_session),
) -> Project:
    repo = ProjectRepository(session)
    return await repo.create(name=body.name, github_url=body.github_url)


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(session: AsyncSession = Depends(get_session)) -> list[Project]:
    return await ProjectRepository(session).list_all()


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
    github: GitHubClient = Depends(get_github_client),
) -> list[dict]:
    """Return recent workflow runs for the configured repo.
    Use the `id` field as input for **GET /github/runs/{run_id}/artifacts**.
    """
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

    CI_WEBHOOK_TOKEN trống → auth disabled (dev mode).
    """
    webhook_token = credentials.credentials if credentials else None
    if settings.CI_WEBHOOK_TOKEN and webhook_token != settings.CI_WEBHOOK_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid or missing webhook token")

    github_url = f"https://github.com/{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}"
    project = await ProjectRepository(session).get_or_create_by_github_url(
        name=f"{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}",
        github_url=github_url,
    )

    processor = SecurityProcessor(session_factory=AsyncSessionLocal)
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
    skip: int = 0,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
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
    filter_kwargs = dict(
        project_id=project_id,
        severity=severity,
        tool=tool,
        status=status,
        category=category,
        q=q,
    )
    total = await repo.count_with_filters(**filter_kwargs)
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    return await repo.list_with_filters(skip=skip, limit=limit, **filter_kwargs)


@router.get("/findings/{finding_id}", response_model=FindingOut)
async def get_finding(
    finding_id: int,
    session: AsyncSession = Depends(get_session),
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


@router.get("/github/runs/{run_id}/findings", response_model=list[FindingOut])
async def get_run_findings(
    run_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[Finding]:
    """Return all findings from a specific GitHub Actions workflow run."""
    return await FindingRepository(session).list_for_run(run_id)

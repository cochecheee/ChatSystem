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
async def list_projects(session: AsyncSession = Depends(get_session)) -> list[Project]:
    return await ProjectRepository(session).list_all()


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
) -> list[dict]:
    """Return recent workflow runs for the configured repo.
    Use the `id` field as input for **GET /github/runs/{run_id}/artifacts**.

    `?project_id=` (V2.9): dùng credentials per-project thay vì env. 404 nếu
    project không tồn tại.
    """
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
    # B2 (future): truyền project để processor.process_run dùng
    # per-project GitHub client. Hiện B2 chưa wire — vẫn dùng env client.
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

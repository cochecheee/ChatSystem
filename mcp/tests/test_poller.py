from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.db import Base
from src.models.entities import Project
from src.services.poller import GitHubPoller


@pytest.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


def _make_poller(db, github_client, processor):
    with patch("src.services.poller.settings") as mock_settings:
        mock_settings.POLLING_INTERVAL_SECONDS = 300
        mock_settings.POLLING_WORKFLOW_NAME = "CI Workflow"
        mock_settings.POLLING_BRANCH = "main"
        mock_settings.GITHUB_OWNER = "myorg"
        mock_settings.GITHUB_REPO = "java-app"
        poller = GitHubPoller(
            processor=processor,
            github_client=github_client,
            session_factory=db,
        )
        poller._github_url = "https://github.com/myorg/java-app"
    return poller


@pytest.mark.asyncio
async def test_poll_processes_new_run(db):
    mock_github = AsyncMock()
    mock_github.list_workflow_runs.return_value = [
        {"id": 1001, "conclusion": "success", "name": "CI Workflow"},
    ]
    mock_processor = AsyncMock()

    poller = _make_poller(db, mock_github, mock_processor)
    await poller._poll()

    mock_processor.process_run.assert_called_once()
    args = mock_processor.process_run.call_args[0]
    assert args[1] == 1001  # github_run_id


@pytest.mark.asyncio
async def test_poll_skips_already_processed_run(db):
    async with db() as session:
        project = Project(
            name="myorg/java-app",
            github_url="https://github.com/myorg/java-app",
            last_processed_run_id=1001,
        )
        session.add(project)
        await session.commit()

    mock_github = AsyncMock()
    mock_github.list_workflow_runs.return_value = [
        {"id": 1001, "conclusion": "success"},
    ]
    mock_processor = AsyncMock()

    poller = _make_poller(db, mock_github, mock_processor)
    await poller._poll()

    mock_processor.process_run.assert_not_called()


@pytest.mark.asyncio
async def test_poll_ingests_failed_but_skips_cancelled(db):
    """A `failure` run is usually the security gate tripping — its SAST
    artifacts carry the findings we need, so it MUST be ingested. `cancelled`
    (and skipped/timed_out) runs have no reliable artifacts and stay skipped.
    """
    mock_github = AsyncMock()
    mock_github.list_workflow_runs.return_value = [
        {"id": 2001, "conclusion": "failure"},
        {"id": 2002, "conclusion": "cancelled"},
    ]
    mock_processor = AsyncMock()

    poller = _make_poller(db, mock_github, mock_processor)
    await poller._poll()

    # failure ingested, cancelled skipped
    mock_processor.process_run.assert_called_once()
    called_run_id = mock_processor.process_run.call_args.args[-1]
    assert called_run_id == 2001


@pytest.mark.asyncio
async def test_poll_updates_last_processed_run_id(db):
    mock_github = AsyncMock()
    mock_github.list_workflow_runs.return_value = [
        {"id": 3001, "conclusion": "success"},
        {"id": 3002, "conclusion": "success"},
    ]
    mock_processor = AsyncMock()

    poller = _make_poller(db, mock_github, mock_processor)
    await poller._poll()

    async with db() as session:
        from sqlalchemy import select
        result = await session.execute(select(Project).where(
            Project.github_url == "https://github.com/myorg/java-app"
        ))
        project = result.scalar_one()

    assert project.last_processed_run_id == 3002


@pytest.mark.asyncio
async def test_poll_creates_project_if_not_exists(db):
    mock_github = AsyncMock()
    mock_github.list_workflow_runs.return_value = []
    mock_processor = AsyncMock()

    poller = _make_poller(db, mock_github, mock_processor)
    await poller._poll()

    async with db() as session:
        from sqlalchemy import select
        result = await session.execute(select(Project))
        projects = result.scalars().all()

    assert len(projects) == 1
    assert "java-app" in projects[0].github_url


@pytest.mark.asyncio
async def test_poll_continues_on_run_error(db):
    mock_github = AsyncMock()
    mock_github.list_workflow_runs.return_value = [
        {"id": 4001, "conclusion": "success"},
        {"id": 4002, "conclusion": "success"},
    ]
    mock_processor = AsyncMock()
    mock_processor.process_run.side_effect = [RuntimeError("GitHub error"), None]

    poller = _make_poller(db, mock_github, mock_processor)
    await poller._poll()  # should not raise

    # Second run should still be attempted
    assert mock_processor.process_run.call_count == 2


# ---------------------------------------------------------------------------
# V2.8 B3 — multi-tenant poller
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multi_tenant_iterates_active_projects(monkeypatch):
    """MULTI_TENANT_ENABLED=true → poll all active projects in parallel.

    Mock 2 active projects + 1 inactive. Verify list_active returns 2,
    processor.process_run called for each new run per project.
    """
    from src.repositories import ProjectRepository
    from src.services import poller as poller_mod

    monkeypatch.setattr(poller_mod.settings, "MULTI_TENANT_ENABLED", True)

    # Mock 2 projects với different runs available
    p1 = MagicMock()
    p1.id = 1
    p1.github_owner = "cochecheee"
    p1.github_repo = "sample-python"
    p1.github_token = "ghp_p1"
    p1.polling_workflow_name = ""
    p1.polling_branch = ""
    p1.last_processed_run_id = 100

    p2 = MagicMock()
    p2.id = 2
    p2.github_owner = "cochecheee"
    p2.github_repo = "SAST_CICD"
    p2.github_token = "ghp_p2"
    p2.polling_workflow_name = ""
    p2.polling_branch = ""
    p2.last_processed_run_id = 200

    # list_active returns 2 projects
    monkeypatch.setattr(
        ProjectRepository, "list_active",
        AsyncMock(return_value=[p1, p2]),
    )

    # Per-project gh.list_workflow_runs → different runs
    gh_p1 = AsyncMock()
    gh_p1.list_workflow_runs = AsyncMock(return_value=[
        {"id": 101, "conclusion": "success"},
        {"id": 102, "conclusion": "success"},
    ])
    gh_p2 = AsyncMock()
    gh_p2.list_workflow_runs = AsyncMock(return_value=[
        {"id": 201, "conclusion": "success"},
    ])

    def fake_for_project(project):
        return gh_p1 if project.id == 1 else gh_p2

    monkeypatch.setattr(
        poller_mod.GitHubClient, "for_project",
        classmethod(lambda cls, project: fake_for_project(project)),
    )

    mock_processor = AsyncMock()
    mock_processor.process_run = AsyncMock()

    # Stub session for last_processed update
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.get = AsyncMock(return_value=None)  # skip update
    mock_session.commit = AsyncMock()

    sf = MagicMock(return_value=mock_session)

    poller = poller_mod.GitHubPoller(
        processor=mock_processor,
        session_factory=sf,
    )

    await poller._poll()

    # process_run gọi cho 3 run (2 từ p1 + 1 từ p2)
    assert mock_processor.process_run.call_count == 3
    calls = {c.args for c in mock_processor.process_run.call_args_list}
    assert (1, 101) in calls
    assert (1, 102) in calls
    assert (2, 201) in calls


@pytest.mark.asyncio
async def test_multi_tenant_empty_active_list(monkeypatch):
    """Không có active project → skip cycle, không crash."""
    from src.repositories import ProjectRepository
    from src.services import poller as poller_mod

    monkeypatch.setattr(poller_mod.settings, "MULTI_TENANT_ENABLED", True)
    monkeypatch.setattr(ProjectRepository, "list_active", AsyncMock(return_value=[]))

    mock_processor = AsyncMock()
    poller = poller_mod.GitHubPoller(processor=mock_processor)
    await poller._poll()
    mock_processor.process_run.assert_not_called()


@pytest.mark.asyncio
async def test_multi_tenant_one_project_fail_does_not_crash_cycle(monkeypatch):
    """1 project lỗi → log + skip, project khác vẫn process."""
    from src.repositories import ProjectRepository
    from src.services import poller as poller_mod

    monkeypatch.setattr(poller_mod.settings, "MULTI_TENANT_ENABLED", True)

    p_ok = MagicMock(id=10, github_owner="x", github_repo="ok", github_token="t",
                    polling_workflow_name="", polling_branch="", last_processed_run_id=0)
    p_bad = MagicMock(id=11, github_owner="x", github_repo="bad", github_token="t",
                     polling_workflow_name="", polling_branch="", last_processed_run_id=0)

    monkeypatch.setattr(
        ProjectRepository, "list_active",
        AsyncMock(return_value=[p_ok, p_bad]),
    )

    gh_ok = AsyncMock()
    gh_ok.list_workflow_runs = AsyncMock(return_value=[{"id": 50, "conclusion": "success"}])
    gh_bad = AsyncMock()
    gh_bad.list_workflow_runs = AsyncMock(side_effect=RuntimeError("GitHub down"))

    monkeypatch.setattr(
        poller_mod.GitHubClient, "for_project",
        classmethod(lambda cls, project: gh_ok if project.id == 10 else gh_bad),
    )

    mock_processor = AsyncMock()
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.get = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()
    sf = MagicMock(return_value=mock_session)

    poller = poller_mod.GitHubPoller(processor=mock_processor, session_factory=sf)
    await poller._poll()

    # ok project vẫn process run 50
    mock_processor.process_run.assert_called_once_with(10, 50)

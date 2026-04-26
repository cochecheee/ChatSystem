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
async def test_poll_skips_failed_runs(db):
    mock_github = AsyncMock()
    mock_github.list_workflow_runs.return_value = [
        {"id": 2001, "conclusion": "failure"},
        {"id": 2002, "conclusion": "cancelled"},
    ]
    mock_processor = AsyncMock()

    poller = _make_poller(db, mock_github, mock_processor)
    await poller._poll()

    mock_processor.process_run.assert_not_called()


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

import asyncio
import os
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import select
from src.services.github_client import GitHubClient
from src.services.processor import SecurityProcessor
from src.models.entities import Project

class GitHubPoller:
    def __init__(self, db_session_factory: async_sessionmaker):
        self.github_client = GitHubClient()
        self.processor = SecurityProcessor()
        self.db_session_factory = db_session_factory
        self.interval = int(os.getenv("POLLING_INTERVAL_SECONDS", "300"))
        self.workflow_name = os.getenv("POLLING_WORKFLOW_NAME", "Security Scans")
        self.owner = os.getenv("GITHUB_OWNER")
        self.repo = os.getenv("GITHUB_REPO")

    async def start(self):
        print(f"🕵️ Poller started: Watching {self.owner}/{self.repo} every {self.interval}s")
        while True:
            try:
                await self._poll()
            except Exception as e:
                print(f"❌ Poller Error: {e}")
            await asyncio.sleep(self.interval)

    async def _poll(self):
        async with self.db_session_factory() as db:
            # 1. Lấy thông tin Project từ DB
            result = await db.execute(select(Project).filter(Project.name == self.repo))
            project = result.scalars().first()
            
            if not project:
                # Nếu chưa có project trong DB, tạo mới để theo dõi
                project = Project(name=self.repo, github_url=f"https://github.com/{self.owner}/{self.repo}")
                db.add(project)
                await db.commit()
                await db.refresh(project)

            # 2. Kiểm tra workflow runs trên GitHub
            runs = await self.github_client.get_workflow_runs(self.owner, self.repo, self.workflow_name)
            
            last_id = project.last_processed_run_id or 0
            for run in runs:
                # Nếu có run mới đã hoàn thành
                if run["id"] > last_id and run["conclusion"] == "completed":
                    print(f"🆕 Found new workflow run: {run['id']}. Fetching artifacts...")
                    
                    # Lấy danh sách artifacts của run này (giả định lấy cái đầu tiên)
                    # Trong thực tế cần gọi thêm API list artifacts, ở đây làm đơn giản theo Plan
                    # await self.processor.process_artifact(artifact_id, project.id, self.owner, self.repo, db)
                    
                    project.last_processed_run_id = run["id"]
                    await db.commit()
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
        # Cấu hình từ file .env (Plan 02-04, Task 3)
        self.interval = int(os.getenv("POLLING_INTERVAL_SECONDS", "300"))
        self.workflow_name = os.getenv("POLLING_WORKFLOW_NAME", "Security Scans")
        self.owner = os.getenv("GITHUB_OWNER")
        self.repo = os.getenv("GITHUB_REPO")

    async def start(self):
        """Khởi chạy vòng lặp Poller ngầm (Lifespan Task)"""
        print(f"🕵️ Poller started: Watching {self.owner}/{self.repo} every {self.interval}s")
        while True:
            try:
                await self._poll()
            except Exception as e:
                print(f"❌ Poller Execution Error: {e}")
            await asyncio.sleep(self.interval)

    async def _poll(self):
        """Logic kiểm tra và kích hoạt Processor (Plan 02-04)"""
        async with self.db_session_factory() as db:
            # Lấy hoặc khởi tạo Project trong DB
            result = await db.execute(select(Project).filter(Project.name == self.repo))
            project = result.scalars().first()
            
            if not project:
                project = Project(name=self.repo, github_url=f"https://github.com/{self.owner}/{self.repo}") # type: ignore
                db.add(project)
                await db.commit()
                await db.refresh(project)

            # Lấy danh sách workflow runs từ GitHub (REQ-2.1)
            runs = await self.github_client.get_workflow_runs(self.owner, self.repo, self.workflow_name)
            
            last_id = project.last_processed_run_id or 0
            for run in runs:
                # Chỉ xử lý run mới hơn và đã hoàn thành thành công (REQ-5.1)
                if run["id"] > last_id and run["conclusion"] == "completed":
                    print(f"🆕 New run detected: {run['id']}. Looking for artifacts...")
                    
                    # Lấy artifact_id từ run_id (Yêu cầu hệ thống phải tự tìm artifact)
                    artifacts = await self.github_client.get_run_artifacts(self.owner, self.repo, run["id"])
                    
                    for art in artifacts:
                        # Kích hoạt processor cho từng artifact tìm thấy
                        await self.processor.process_artifact(
                            artifact_id=art["id"],
                            project_id=project.id,
                            owner=self.owner,
                            repo=self.repo,
                            db=db
                        )
                    
                    # Cập nhật last_processed_run_id để không quét lại (Plan 02-04 truths)
                    project.last_processed_run_id = run["id"]
                    await db.commit()
                    print(f"✅ Run {run['id']} processed and updated in DB.")
import asyncio
from typing import List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.github_client import GitHubClient
from src.core.guardrails import ScrubbingService, InjectionGuardrail
from src.services.normalizer import NormalizerFactory
from src.services.enricher import EnricherService
from src.models.entities import Artifact, Finding

class SecurityProcessor:
    def __init__(self):
        self.github = GitHubClient()
        self.scrubber = ScrubbingService()
        self.guardrail = InjectionGuardrail()
        self.enricher = EnricherService()

    async def process_artifact(self, artifact_id: int, project_id: int, owner: str, repo: str, db: AsyncSession):
        """Dây chuyền xử lý: Tải -> Làm sạch -> Chuyển đổi -> Làm giàu -> Lưu DB"""
        print(f"🔄 Đang xử lý Artifact ID: {artifact_id}...")
        
        # 1. Tải từ GitHub
        raw_files = await self.github.fetch_artifact(owner, repo, artifact_id)
        
        # Tạo bản ghi Artifact trong DB
        new_artifact = Artifact(github_artifact_id=artifact_id, project_id=project_id, status="processing")
        db.add(new_artifact)
        await db.commit()
        await db.refresh(new_artifact)

        total_findings = 0
        for file in raw_files:
            # 2. Làm sạch dữ liệu (Scrubbing)
            safe_content = self.scrubber.scrub_content(file["content"])
            
            # 3. Chuyển đổi định dạng (Normalize)
            normalizer = NormalizerFactory.get_normalizer(file["file_name"])
            findings_data = normalizer.normalize(safe_content)
            
            for f_data in findings_data:
                # 4. Kiểm tra mã độc (Injection Guardrail)
                if not self.guardrail.validate_finding(f_data.message):
                    continue
                
                # 5. Làm giàu dữ liệu (Enrich)
                enriched_f = self.enricher.enrich_finding(f_data)
                
                # 6. Lưu vào DB
                db_finding = Finding(
                    artifact_id=new_artifact.id,
                    **enriched_f.model_dump()
                )
                db.add(db_finding)
                total_findings += 1

        new_artifact.status = "completed"
        await db.commit()
        print(f"✅ Xử lý xong! Đã lưu {total_findings} lỗi vào Database.")
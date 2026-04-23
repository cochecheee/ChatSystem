import asyncio
from typing import List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.services.github_client import GitHubClient
from src.core.guardrails import ScrubbingService, InjectionGuardrail
from src.services.normalizer import NormalizerFactory
from src.services.enricher import EnricherService
from src.models.entities import Artifact, Finding
from src.models.schemas import generate_dedup_hash

class SecurityProcessor:
    def __init__(self):
        self.github = GitHubClient()
        self.scrubber = ScrubbingService()
        self.guardrail = InjectionGuardrail()
        self.enricher = EnricherService()

    async def process_artifact(self, artifact_id: int, project_id: int, owner: str, repo: str, db: AsyncSession):
        """Hợp nhất: Tải -> Làm sạch -> Chuẩn hóa -> Làm giàu -> Lưu DB (Plan 02-04)"""
        print(f"🔄 Processing Artifact {artifact_id} for project {project_id}...")

        raw_files = await self.github.fetch_artifact(owner, repo, artifact_id)
        if not raw_files:
            print(f"⚠️ No security files found in artifact {artifact_id}")
            return

        # Tạo bản ghi Artifact
        new_artifact = Artifact(github_artifact_id=artifact_id, project_id=project_id, status="processing")
        db.add(new_artifact)
        await db.commit()
        await db.refresh(new_artifact)

        total_saved = 0
        for file in raw_files:
            # Ta thực hiện Normalizer trước để lấy ra message, sau đó mới Scrubbing message
            normalizer = NormalizerFactory.get_normalizer(file["file_name"])
            findings_data = normalizer.normalize(file["content"])
            
            for f_data in findings_data:
                # Dựa trên: Tool + File + Rule + Message
                f_hash = generate_dedup_hash(f_data.rule_id, f_data.file_path, f_data.message)
                
                # Kiểm tra hash trong DB
                existing = await db.execute(select(Finding).filter(Finding.fingerprint == f_hash))
                if existing.scalars().first():
                    continue # Bỏ qua lỗi đã tồn tại

                f_data.message = self.scrubber.scrub_content(f_data.message)
                if not self.guardrail.validate_finding(f_data.message):
                    continue

                enriched_f = self.enricher.enrich_finding(f_data)

                db_finding = Finding(
                    artifact_id=new_artifact.id,
                    fingerprint=f_hash, # Lưu hash để so sánh lần sau
                    **enriched_f.model_dump()
                )
                db.add(db_finding)
                total_saved += 1

        new_artifact.status = "completed"
        await db.commit()
        print(f"✅ Finished! Saved {total_saved} new enriched findings.")
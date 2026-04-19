from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.core.db import get_db
from src.models.entities import Finding
from src.services.processor import SecurityProcessor

router = APIRouter(prefix="/artifacts", tags=["Artifacts"])
processor = SecurityProcessor()

@router.get("/findings")
async def get_all_findings(db: AsyncSession = Depends(get_db)):
    """Lấy danh sách tất cả các lỗi bảo mật đã quét được"""
    result = await db.execute(select(Finding).order_by(Finding.id.desc()))
    return result.scalars().all()

@router.post("/process/{project_id}/{artifact_id}")
async def trigger_processing(
    project_id: int, 
    artifact_id: int, 
    owner: str, 
    repo: str, 
    background_tasks: BackgroundTasks, 
    db: AsyncSession = Depends(get_db)
):
    """Kích hoạt quy trình xử lý chạy ngầm"""
    background_tasks.add_task(processor.process_artifact, artifact_id, project_id, owner, repo, db)
    return {"message": "Processing started in background", "artifact_id": artifact_id}
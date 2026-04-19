from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, List, Any
import hashlib

class FindingBase(BaseModel):
    tool: str
    rule_id: str
    severity: str
    message: str
    file_path: str
    line_number: int

class FindingCreate(FindingBase):
    raw_data: Any
    cwe_id: Optional[str] = None
    cvss_score: Optional[str] = None

class FindingOut(FindingBase):
    id: int
    normalized_at: datetime
    model_config = ConfigDict(from_attributes=True)

def generate_dedup_hash(rule_id: str, file_path: str, message: str) -> str:
    """Tạo mã hash để tránh trùng lặp lỗi"""
    content = f"{rule_id}|{file_path}|{message}"
    return hashlib.sha256(content.encode()).hexdigest()
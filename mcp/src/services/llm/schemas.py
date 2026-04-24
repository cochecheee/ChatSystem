from pydantic import BaseModel
from typing import Optional, Literal

class AnalysisOutput(BaseModel):
    """Cấu trúc phản hồi từ AI Gemini (7 trường thông tin)"""
    vulnerability_id: str      # ID tham chiếu từ lỗi gốc
    explanation_vi: str        # Giải thích chi tiết bằng tiếng Việt
    impact_vi: str             # Đánh giá tác động bằng tiếng Việt
    remediation_diff: str      # Mã sửa lỗi định dạng Unified Diff
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    cwe_reference: str         # Ví dụ: "CWE-89: SQL Injection"
    confidence: Literal["HIGH", "MEDIUM", "LOW"]

class AnalysisRequest(BaseModel):
    """Dữ liệu đầu vào để gửi cho AI phân tích"""
    finding_id: str
    tool_name: str
    rule_id: str
    message: str
    file_path: str
    line_number: int
    cwe_id: Optional[str] = None
    code_context: str          # 30 dòng code xung quanh vị trí lỗi
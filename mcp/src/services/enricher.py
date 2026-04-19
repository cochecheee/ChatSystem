from typing import Optional, Any
from cwe2.database import Database

class EnricherService:
    def __init__(self):
        # Database CWE (Common Weakness Enumeration)
        self.cwe_db = Database()

    def enrich_finding(self, finding_create: Any):
        """Bổ sung thông tin CWE và điểm số CVSS dựa trên mức độ nghiêm trọng"""
        # Giả định mapping mức độ nghiêm trọng sang điểm số CVSS cơ bản
        severity_map = {
            "error": "7.5 (High)",
            "warning": "5.0 (Medium)",
            "note": "3.0 (Low)",
            "critical": "9.0 (Critical)"
        }
        
        if not finding_create.cvss_score:
            finding_create.cvss_score = severity_map.get(finding_create.severity.lower(), "0.0")

        # Tra cứu tên lỗi CWE nếu có ID
        if finding_create.cwe_id:
            try:
                cwe_obj = self.cwe_db.get(finding_create.cwe_id.replace("CWE-", ""))
                # Bạn có thể thêm mô tả chi tiết từ cwe_obj vào message ở đây
            except:
                pass
        
        return finding_create
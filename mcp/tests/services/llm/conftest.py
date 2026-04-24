import pytest
from unittest.mock import AsyncMock
import json

@pytest.fixture
def mock_gemini_client():
    """Giả lập GeminiClient để chạy test không cần API Key (Plan 03-01, Task 3)"""
    mock = AsyncMock()
    
    # Giả lập một kết quả trả về đúng cấu trúc AnalysisOutput
    sample_response = {
        "vulnerability_id": "test-123",
        "explanation_vi": "Đây là một lỗ hổng giả lập để kiểm tra hệ thống.",
        "impact_vi": "Có thể làm lộ dữ liệu người dùng.",
        "remediation_diff": "--- file.java\n+++ file.java\n- old code\n+ new code",
        "severity": "HIGH",
        "cwe_reference": "CWE-89",
        "confidence": "HIGH"
    }
    
    # Mặc định mock sẽ trả về chuỗi JSON này
    mock.generate.return_value = json.dumps(sample_response)
    return mock

@pytest.fixture
def sample_analysis_request():
    """Dữ liệu đầu vào mẫu cho việc phân tích"""
    return {
        "finding_id": "finding_001",
        "tool_name": "Semgrep",
        "rule_id": "java.lang.security.audit.sql-injection",
        "message": "Potential SQL Injection",
        "file_path": "src/main/java/App.java",
        "line_number": 42,
        "cwe_id": "CWE-89",
        "code_context": "String query = 'SELECT * FROM users WHERE id = ' + id;"
    }
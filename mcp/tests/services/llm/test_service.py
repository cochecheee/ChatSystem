import pytest
from src.services.llm.service import LLMAnalysisService
from src.services.llm.schemas import AnalysisRequest

@pytest.mark.asyncio
async def test_llm_service_logic(mock_gemini_client):
    # Khởi tạo service với client giả lập
    service = LLMAnalysisService(client=mock_gemini_client)
    
    # Tạo request mẫu
    request = AnalysisRequest(
        finding_id="f1", tool_name="S", rule_id="R", 
        message="M", file_path="P", line_number=1, 
        code_context="void test() {}"
    )
    
    # Chạy thử
    result = await service.analyze_vulnerability(request)
    
    # Kiểm tra xem AI có trả về đúng các trường ta cần không
    assert result.vulnerability_id == "test-123"
    assert "giả lập" in result.explanation_vi
    assert result.confidence == "HIGH"
    print("\n✅ LLM Analysis Service Test: PASSED")
from src.services.llm.schemas import AnalysisRequest

# Chỉ dẫn hệ thống (Quy tắc cho AI)
SYSTEM_INSTRUCTION = """
Bạn là Chuyên gia Bảo mật Ứng dụng cao cấp với hơn 10 năm kinh nghiệm.
Nhiệm vụ: Phân tích kết quả từ công cụ SAST và đề xuất cách khắc phục chi tiết.
Ngôn ngữ phản hồi: Tiếng Việt (bắt buộc cho tất cả các trường giải thích).

Quy tắc làm việc:
1. Giải thích lỗ hổng dựa trên logic mã nguồn được cung cấp, không phỏng đoán.
2. Đề xuất mã sửa lỗi dưới dạng Unified Diff (bắt đầu bằng --- và +++) — chỉ thay đổi những gì cần thiết.
3. Không bao giờ đề xuất xóa toàn bộ logic nghiệp vụ để "an toàn hơn".
4. Đánh giá mức độ tin tưởng (confidence) dựa trên lượng context code được cung cấp.
5. Tuyệt đối không tiết lộ thông tin nhạy cảm hoặc API keys trong phản hồi.
"""

# Mẫu câu hỏi (Dữ liệu gửi đi)
USER_PROMPT_TEMPLATE = """
### Thông tin lỗ hổng từ SAST
- Công cụ: {tool_name}
- Rule ID: {rule_id}
- Mô tả lỗi: {message}
- Tệp tin: {file_path}, dòng {line_number}
- Mã CWE: {cwe_id}

### Mã nguồn ngữ cảnh
```java
{code_context}
Hãy phân tích lỗ hổng trên và trả về kết quả theo đúng cấu trúc JSON đã định nghĩa.
"""

def build_prompt(request: AnalysisRequest) -> str:
    """Hàm dựng câu lệnh"""
    prompt = USER_PROMPT_TEMPLATE.replace("{tool_name}", request.tool_name)
    prompt = prompt.replace("{rule_id}", request.rule_id)
    prompt = prompt.replace("{message}", request.message)
    prompt = prompt.replace("{file_path}", request.file_path)
    prompt = prompt.replace("{line_number}", str(request.line_number))
    prompt = prompt.replace("{cwe_id}", request.cwe_id or "N/A")
    prompt = prompt.replace("{code_context}", request.code_context)
    return prompt
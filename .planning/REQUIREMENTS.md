# System Requirements: Security-Integrated CI/CD System

## Functional Requirements

### 1. CI/CD Pipeline & SAST Integration
- Phải hỗ trợ trigger pipeline từ GitHub Events (Push, Pull Request).
- Phải tích hợp ít nhất 5 công cụ SAST: Semgrep, CodeQL, ESLint, SpotBugs, OWASP Dependency-Check.
- Phải tạo và upload các kết quả quét dưới định dạng SARIF hoặc XML lên GitHub Artifacts.
- Phải có cơ chế Security Gate để chặn các Pull Request vi phạm chính sách bảo mật (ví dụ: phát hiện lỗ hổng CRITICAL).

### 2. MCP Gateway (Model Context Protocol) Server
- Phải tự động thu thập (fetch) artifacts từ GitHub sau khi pipeline hoàn tất.
- Phải chuẩn hóa (normalize) dữ liệu từ nhiều định dạng khác nhau (SARIF, XML, JSON) về một schema thống nhất.
- Phải thực hiện khử thông tin nhạy cảm (sanitization): loại bỏ PII, Secrets, Environment Variables trước khi gửi dữ liệu cho AI.
- Phải có cơ chế ngăn chặn Prompt Injection (Guardrails).
- Phải làm giàu dữ liệu (enrichment) bằng cách tra cứu CWE, OWASP categories và CVSS scores.

### 3. AI Analysis & Remediation (LLM Orchestrator)
- Phải sử dụng mô hình Gemini (phiên bản 2.5 hoặc 3.1) để phân tích lỗ hổng.
- Phải cung cấp giải thích chi tiết (Vulnerability Explanation) bằng tiếng Việt.
- Phải đề xuất đoạn mã sửa lỗi (Remediation) cụ thể dựa trên ngữ cảnh mã nguồn.
- Phải kiểm tra tính hợp lệ của phản hồi từ LLM (Output Validation).

### 4. Web Dashboard (Tích hợp ChatOps)
- Phải hiển thị danh sách lỗ hổng và trạng thái pipeline theo thời gian thực (Polling mỗi 15 giây).
- Phải tích hợp giao diện Chat (ChatOps) để tương tác trực tiếp với AI assistant.
- Phải hỗ trợ các lệnh trong Chat panel: `/status`, `/scan`, `/results`, `/explain`, `/fix`, `/rerun`, `/approve`, `/report`.
- Phải hiển thị biểu đồ thống kê mức độ nghiêm trọng của lỗ hổng.
- Phải phân quyền người dùng dựa trên GitHub team membership khi truy cập dashboard và sử dụng lệnh chat.

### 5. Storage Layer
- Phải lưu trữ thông tin lỗ hổng và lịch sử phân tích vào SQLite database.

## Non-Functional Requirements
- **Security:** Bảo vệ các API keys, Secrets của hệ thống. Tuân thủ nguyên tắc "security by design".
- **Reliability:** Cơ chế Retry khi fetch artifacts từ GitHub.
- **Scalability:** Thiết kế module cho phép thêm công cụ SAST mới dễ dàng.
- **Performance:** Thời gian phản hồi của AI assistant phải ở mức chấp nhận được cho workflow hàng ngày.

# Security-Integrated CI/CD System (Chat System)

Dự án đồ án tốt nghiệp - Hệ thống tích hợp bảo mật vào quy trình CI/CD hỗ trợ bởi AI (Gemini).

## Project Structure
- `mcp/`: MCP Gateway Server (Python FastAPI).
- `dashboard/`: Web Dashboard (React + Vite).
- `.planning/`: Kế hoạch và yêu cầu hệ thống (Framework GSD).
- `.github/workflows/`: Các pipeline CI/CD tích hợp SAST.

## Setup
### MCP Gateway
1. Chuyển vào thư mục `mcp/`.
2. Tạo môi trường ảo: `python -m venv venv`.
3. Kích hoạt môi trường: `venv\Scripts\activate` (Windows) hoặc `source venv/bin/activate` (Linux/Mac).
4. Cài đặt thư viện: `pip install -r requirements.txt`.
5. Chạy server: `uvicorn src.main:app --reload`.

### Web Dashboard
1. Chuyển vào thư mục `dashboard/`.
2. Cài đặt dependencies: `npm install`.
3. Chạy dev server: `npm run dev`.

## Features
- CI/CD SAST Scans (Semgrep, CodeQL, etc.)
- MCP Middleware for Data Normalization & Guardrails.
- LLM (Gemini) vulnerability analysis & remediation suggestions.
- Interactive Dashboard & ChatOps commands.

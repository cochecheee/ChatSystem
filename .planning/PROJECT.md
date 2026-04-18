# Project: Security-Integrated CI/CD System

## Overview
Dự án nhằm mục đích tích hợp bảo mật vào quy trình CI/CD (DevSecOps) bằng cách sử dụng các công cụ SAST (Semgrep, CodeQL, ESLint, SpotBugs, OWASP Dependency-Check) và tận dụng sức mạnh của Large Language Models (Gemini) để phân tích lỗ hổng và đề xuất khắc phục tự động.

## Architecture
Hệ thống được thiết kế theo mô hình module hóa bao gồm 7 thành phần chính:
1. **Source Code Repository:** GitHub.
2. **CI/CD Pipeline:** GitHub Actions tích hợp SAST tools.
3. **MCP Gateway:** Middleware chuẩn hóa dữ liệu từ SAST artifacts và áp dụng Guardrails cho AI.
4. **LLM Orchestrator:** Phân tích lỗ hổng sử dụng Gemini API.
5. **Web Dashboard:** Giao diện chính hiển thị kết quả, thống kê và điều khiển pipeline (React + FastAPI). Tích hợp tính năng Chat (ChatOps) để tương tác trực tiếp với AI assistant qua các lệnh tự nhiên.
6. **Storage Layer:** SQLite lưu trữ kết quả đã chuẩn hóa và phân tích từ AI.

## Technical Stack
- **Backend:** Python (FastAPI, SQLAlchemy, Pydantic).
- **Frontend:** React (Vite, TypeScript).
- **AI:** Google Gemini (Generative AI).
- **Security:** Semgrep, CodeQL, ESLint, SpotBugs, OWASP Dependency-Check.
- **CI/CD:** GitHub Actions.
- **Database:** SQLite.

## Goals
- Phát hiện sớm các lỗ hổng bảo mật ngay trong quá trình phát triển (Shift Left Security).
- Cung cấp giải thích chi tiết và gợi ý code khắc phục tự động thông qua AI.
- Tự động hóa việc kiểm duyệt bảo mật (Security Gate).
- Tăng cường khả năng tương tác của developer thông qua ChatOps và Dashboard trực quan.

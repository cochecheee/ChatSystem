# 01 — Tổng quan

## Bản chất project

**chat-system** = SAST/SCA dashboard với AI fix tiếng Việt, kèm thư viện GitHub Actions tái sử dụng.

Đồ án tốt nghiệp. Mục đích: cho phép bất kỳ project nào (Java/Python/Node/Go) plug vào → có sẵn pipeline security scan + dashboard hiển thị finding + AI giải thích & đề xuất fix.

## v0.1.0 (defense-ready, done)

- 6 trang dashboard thật (Overview/Pipelines/Vulnerabilities/SCA/Chat/Reports/Settings)
- Backend FastAPI + SQLite + Gemini AI
- 200/200 pytest pass, smoke test 7 endpoint
- Docker stack (`docker-compose.yml`)
- Composite Action `action.yml` (root) — webhook notify
- Multi-tenant Project scaffolding (cột credentials, runtime VẪN single-tenant từ `.env`)
- Demo collateral đầy đủ: `docs/demo-script.md`, `docs/preflight-checklist.md`

## V2 (DevSecOps template, đang làm)

**Tầm nhìn**: chat-system biến thành **template**. Project khác chỉ viết 10 dòng `uses: cochecheee/sast-action@v0.2.0` → tự có CI/CD/DAST/Monitor.

### Sub-phase V2

| Phase | Trạng thái | Mô tả |
|---|---|---|
| V2.1.1 | ✅ | Refactor monolithic `action.yml` → 3 composite + reusable workflow |
| V2.1.2 | ✅ | Python sample (Flask vulnerable, 5 lỗi cố ý) |
| V2.1.3 | ✅ | Tách `actions/` ra repo riêng `cochecheee/sast-action`. Tách `examples/sample-python/` ra repo `cochecheee/sample-python`. |
| V2.1.4 | ✅ | Deploy mcp lên Render free tier (Blueprint config) |
| V2.1.5 | ✅ | Fix ingest profile + production CORS |
| V2.2 | ⏳ | CD: build image inheritor + deploy Render staging |
| V2.3 | ⏳ | Runtime DAST (OWASP ZAP) + daily Trivy CVE re-scan |
| V2.4 | ⏳ | Monitor + email alert (Sentry + SMTP) |
| V2.5 | ⏳ | Deploy dashboard lên Render Static Site |
| Tag | 🏁 | `v0.2.0` sau khi V2.5 verify end-to-end |

## Stack tổng

```
Backend     FastAPI 0.115  +  SQLAlchemy 2.0 async  +  aiosqlite
AI          Google Gemini API (gemini-2.5-flash, structured output)
Frontend    React 19  +  Vite 8  +  TypeScript  +  Sentinel design
Auth        JWT + RBAC (developer / security_lead / admin)
Tools       Semgrep, CodeQL, SpotBugs, ESLint, Trivy, Bandit, Safety,
            OWASP Dep-Check, gosec, OWASP ZAP (V2.3)
Hosting     Render free tier (mcp Web Service)
            Local dev (dashboard) — Static Site deploy ở V2.5
```

## Số liệu

- ~25 commit V2 sau khi v0.1.0 đóng băng
- 3 repo độc lập (chat-system, sast-action, sample-python)
- 4 ngôn ngữ inheritor được hỗ trợ
- 117 artifact, 8280 Trivy finding ở DB local trước cleanup
- 305KB JS bundle production

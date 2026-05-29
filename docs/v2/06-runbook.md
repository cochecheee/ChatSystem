# 06 — Runbook: chạy & fix nhanh

## 6.1 Chạy local 3 service

### Terminal 1 — Backend
```powershell
cd D:\School\DoAnTotNghiep\chat-system\mcp
.venv\Scripts\activate
uvicorn src.main:app --reload --port 8000
```
Swagger: http://localhost:8000/docs

### Terminal 2 — Frontend
```powershell
cd D:\School\DoAnTotNghiep\chat-system\dashboard
npm install   # lần đầu
npm run dev
```
Dashboard: http://localhost:5173

### Terminal 3 — Ngrok (nếu cần GitHub webhook hit local)
```powershell
D:\School\DoAnTotNghiep\ngrok-v3-stable-windows-amd64\ngrok.exe http 8000
```

## 6.2 Env vars tối thiểu (`mcp/.env`)

```ini
DATABASE_URL=sqlite+aiosqlite:///./mcp.db
SECRET_KEY=<random 32+ chars; python -c "import secrets; print(secrets.token_hex(32))">
GITHUB_TOKEN=ghp_xxx
GITHUB_OWNER=cochecheee
GITHUB_REPO=sample-python
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-2.5-flash
APP_ENV=development
CI_WEBHOOK_TOKEN=<shared secret với GitHub Actions step>
```

Flag bật khi cần:
```ini
MULTI_TENANT_ENABLED=true
RBAC_PER_PROJECT=true
MONITOR_ENABLED=true
MONITOR_TARGETS=1:https://sample-python-latest.onrender.com/health
```

Frontend env (`dashboard/.env.local`):
```ini
VITE_API_URL=http://localhost:8000
```

## 6.3 Common bugs đã gặp

### Bug: `WinError 10013` khi start uvicorn
Port 8000 bị process khác giữ. Diagnose:
```powershell
Get-NetTCPConnection -LocalPort 8000 | Select OwningProcess
Get-Process -Id <pid>
```
Fix: `Stop-Process -Id <pid> -Force` hoặc đổi `--port 8001`.

### Bug: SARIF lớn parse ra 0 finding
Triệu chứng: codeql.sarif 700KB+ silent drop. Nguyên do (V2.7 fix): regex email
ăn vào `\n@app.route` Python decorator → `\[EMAIL_SCRUBBED]` → invalid JSON escape.
Fix đã apply: `scrub_content` skip JSON content, chỉ `scrub_text` per-field
post-parse (xem `core/guardrails.py:35`).

### Bug: `integer out of range` insert run_id trên Postgres
GitHub workflow run ID 64-bit. Fix: `BigInteger` cho `last_processed_run_id`,
`github_run_id` (xem `models/entities.py:33`).

### Bug: `MissingGreenlet` khi serialize Finding
Pydantic `FindingOut` đọc `finding.project_id` (computed property) → traverse
`Finding.artifact.project_id` → async lazy-load trong sync context. Fix V3.2: 
`selectinload(Finding.artifact)` ở mọi repository query (`finding_repo.py:32`).

### Bug: webhook 403 trên Render
`CI_WEBHOOK_TOKEN` không khớp giữa repo chat-system và repo target. Diagnose:
```bash
curl -i -X POST https://mcp-l958.onrender.com/webhook/pipeline-complete \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"run_id": 1, "pipeline_status": "test"}'
```
Phải trả 202. 403 = token sai. Xem `GET /health/flags` để verify Render env.

### Bug: Production refuse start
`main.py:_enforce_production_safety` fail-fast nếu `APP_ENV=production` mà
`SECRET_KEY`/`CI_WEBHOOK_TOKEN`/`CORS_ORIGINS` rỗng. Xem log Render để biết
field nào thiếu.

### Bug: CORS preflight fail
Trong dev `APP_ENV=development` → wildcard `*` + `allow_credentials=false`.
Prod cần `CORS_ORIGINS=https://dashboard-zyy0.onrender.com` rồi `allow_credentials=true`. Browser từ chối `*` + credentials cùng lúc.

## 6.4 Test commands

```bash
cd mcp
pytest tests/ -q                              # ~3s, 305 tests
pytest tests/test_normalizer.py -v            # focus 1 module
pytest tests/ --cov=src --cov-report=html     # coverage

cd dashboard
npm run test:e2e                              # Playwright headless (TEST_MODE=1)
npm run test:e2e:ui                           # debug UI mode
```

## 6.5 Reprocess 1 workflow run

UI: Pipelines → click run → "Reprocess" button.

CLI:
```powershell
curl -X POST http://localhost:8000/github/runs/<run_id>/reprocess
```

Sẽ wipe Artifact + Finding cho run đó, schedule background task fetch lại từ GitHub.

## 6.6 Deploy lên Render

`render.yaml` đã định nghĩa 2 service. Push lên master → Render auto-redeploy
(nếu auto-deploy bật trên dashboard).

Force redeploy không đổi code:
```powershell
git commit --allow-empty -m "redeploy"
git push
```

Postgres free Render: 256MB. `prune_loop` xoá `uptime_checks` >7 ngày để
tránh đầy.

## 6.7 Smoke test sau deploy

```bash
# Health
curl -m 60 https://mcp-l958.onrender.com/health

# Flags (verify env vào đúng)
curl https://mcp-l958.onrender.com/health/flags

# Projects
curl https://mcp-l958.onrender.com/projects

# Dashboard
Start-Process https://dashboard-zyy0.onrender.com
```

## 6.8 Đọc khi bạn quên

- Tại sao field này là int 0/1 thay vì bool? → `models/entities.py` doc string của `Project.active`
- Tại sao 2 lần scrub? → `core/guardrails.py:scrub_content` doc
- Tại sao webhook idempotent? → `services/processor.py:process_run:126`
- Tại sao process_run accept `project_id` thay vì ORM `project`? → cùng file line 64
- Tại sao memberships trong JWT? → `core/auth.py:create_access_token`

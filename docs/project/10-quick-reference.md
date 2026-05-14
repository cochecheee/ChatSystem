# 10 — Quick Reference

Copy-paste commands cho common task.

## Local dev

### Chạy backend + frontend cùng lúc
```powershell
cd D:\School\DoAnTotNghiep\chat-system
.\start.bat all
```

### Chạy riêng
```powershell
.\start.bat backend     # uvicorn :8000
.\start.bat frontend    # vite :5173
.\start.bat ngrok       # public tunnel (nếu cần)
```

### Stop tất cả
```powershell
.\stop.bat
```

### Run tests
```powershell
.\dev.bat test          # 200 pytest backend
.\dev.bat smoke         # 7-endpoint live check (cần backend up)
.\dev.bat build         # vite production build
.\dev.bat e2e           # playwright E2E
.\dev.bat lint          # GitHub Actions workflow lint
```

### DB management
```powershell
.\dev.bat migrate       # multi-tenant column migration
.\dev.bat reset         # WIPE findings + artifacts (xác nhận trước)
.\dev.bat clean         # remove orphan failed artifacts
```

## Render deploy

### Push để trigger redeploy
```powershell
cd D:\School\DoAnTotNghiep\chat-system
git add .
git commit -m "..."
git push origin ft/imp-fe
# Render auto-rebuild ~3 phút
```

### Check Render service status
```powershell
curl -m 60 https://mcp-l958.onrender.com/health
```

### Manual reprocess 1 GitHub run
```powershell
curl -X POST https://mcp-l958.onrender.com/github/runs/<run_id>/reprocess
```

### Force project create
```powershell
curl -X POST https://mcp-l958.onrender.com/projects `
  -H "Content-Type: application/json" `
  -d '{"name":"<project name>","github_url":"https://github.com/<owner>/<repo>"}'
```

## sast-action library

### Push update + tag mới
```powershell
cd D:\School\DoAnTotNghiep\sast-action
git add .
git commit -m "..."
git push origin master

# Tag stable
git tag v0.3.0
git push origin v0.3.0
```

### Inheritor pin tag
```yaml
# Sửa .github/workflows/security.yml ở inheritor:
uses: cochecheee/sast-action/.github/workflows/sast-ci.yml@v0.3.0
```

## Inheritor mới

### Thêm 1 repo Java/Python/Node/Go vào dashboard (SAST only)

```yaml
# 1. Tạo file .github/workflows/security.yml ở inheritor:
name: Security
on: [push, pull_request, workflow_dispatch]

permissions:
  contents: read
  security-events: write
  actions: read

jobs:
  security:
    uses: cochecheee/sast-action/.github/workflows/sast-ci.yml@master
    with:
      language: python   # hoặc java/node/go
    secrets:
      dashboard_url:   ${{ secrets.MCP_GATEWAY_URL }}
      dashboard_token: ${{ secrets.MCP_WEBHOOK_TOKEN }}
```

### Thêm inheritor mới (SAST + CD deploy Render — V2.2)

```yaml
jobs:
  security:
    uses: cochecheee/sast-action/.github/workflows/sast-ci.yml@master
    with:
      language: python
      deploy: true
      image_repo: cochecheee/<repo-name>
      dockerfile: Dockerfile
      build_context: .
    secrets:
      dashboard_url:      ${{ secrets.MCP_GATEWAY_URL }}
      dashboard_token:    ${{ secrets.MCP_WEBHOOK_TOKEN }}
      docker_username:    ${{ secrets.DOCKER_USERNAME }}
      docker_password:    ${{ secrets.DOCKER_PASSWORD }}
      render_deploy_hook: ${{ secrets.RENDER_DEPLOY_HOOK }}
```

Setup steps cho CD: xem [04-deploy.md → Staging service cho inheritor](04-deploy.md#staging-service-cho-inheritor-v22).

```powershell
# 2. Set 2 secret ở inheritor GitHub:
#    Settings → Secrets → Actions
#    MCP_GATEWAY_URL = https://mcp-l958.onrender.com
#    MCP_WEBHOOK_TOKEN = <same as CI_WEBHOOK_TOKEN ở Render>

# 3. Tạo Project row trong mcp:
curl -X POST https://mcp-l958.onrender.com/projects `
  -H "Content-Type: application/json" `
  -d '{"name":"<repo display name>","github_url":"https://github.com/<owner>/<repo>"}'

# 4. Push trigger CI:
git commit --allow-empty -m "ci: smoke verify"
git push
```

## API endpoints reference

| Route | Method | Mô tả |
|---|---|---|
| `/health` | GET | Healthcheck |
| `/projects` | GET/POST | List + create projects |
| `/projects/{id}` | DELETE | Remove project |
| `/projects/{id}/integration` | GET | Copy-paste snippet cho inheritor |
| `/webhook/pipeline-complete` | POST | CI notify (Bearer auth) |
| `/findings` | GET | List with `category=sast\|deps`, supports pagination |
| `/findings/{id}` | GET | Detail 1 finding |
| `/findings/{id}/analyze` | POST | Trigger Gemini AI fix |
| `/stats/overview` | GET | KPI cho Overview page |
| `/stats/latest-scan` | GET | Stats run mới nhất |
| `/stats/runs` | GET | Pass/fail trend |
| `/github/runs` | GET | List GitHub workflow runs |
| `/github/runs/{run_id}/reprocess` | POST | Force re-ingest |
| `/api/chat/message` | POST | Natural language Q&A |
| `/api/chat/command` | POST | Slash command |
| `/api/auth/token` | POST | JWT login |
| `/docs` | GET | Swagger UI |

## Env vars cheatsheet

| Var | Where | Mô tả |
|---|---|---|
| `DATABASE_URL` | mcp/.env, render.yaml | SQLAlchemy URL |
| `APP_ENV` | mcp/.env, render.yaml | `development` \| `production` |
| `GITHUB_TOKEN` | Render secret | PAT scope: repo+workflow |
| `GITHUB_OWNER`, `GITHUB_REPO` | render.yaml | Single-tenant poller target |
| `POLLING_WORKFLOW_NAME` | render.yaml | Match `name:` ở inheritor workflow |
| `POLLING_INTERVAL_SECONDS` | render.yaml | Poll cycle |
| `GEMINI_API_KEY` | Render secret | Google AI Studio key |
| `GEMINI_MODEL` | render.yaml | `gemini-2.5-flash` |
| `SECRET_KEY` | Render secret | JWT signing key (32+ chars) |
| `CI_API_KEY` | render.yaml | API key cho /artifacts/process. Trống = tắt auth. |
| `CI_WEBHOOK_TOKEN` | Render secret | Webhook Bearer. Match `MCP_WEBHOOK_TOKEN` ở inheritor. |
| `CORS_ORIGINS` | render.yaml | Comma-separated dashboard URLs (production only) |
| `VITE_API_URL` | dashboard/.env.local | Frontend base API URL |

## Path reference

| Asset | Path |
|---|---|
| chat-system repo | `D:\School\DoAnTotNghiep\chat-system` (`ft/imp-fe`) |
| sast-action repo | `D:\School\DoAnTotNghiep\sast-action` (`master`) |
| sample-python repo | `D:\School\DoAnTotNghiep\sample-python` (`main`) |
| ngrok binary | `D:\School\DoAnTotNghiep\ngrok-v3-stable-windows-amd64\ngrok.exe` |
| Backend venv | `D:\School\DoAnTotNghiep\chat-system\mcp\.venv\Scripts\` |
| Local SQLite | `D:\School\DoAnTotNghiep\chat-system\mcp\mcp.db` |
| .env files | `mcp/.env`, `dashboard/.env.local` (gitignored) |
| Render URL | https://mcp-l958.onrender.com |

## Git identity

Local config (`git config user.{name,email}`):
```
user.name  = cochecheee
user.email = buitien747@gmail.com
```

Set ở cả 3 repo (chat-system, sast-action, sample-python).

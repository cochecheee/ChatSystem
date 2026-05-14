# 04 — Deploy

## Render Blueprint

File: `render.yaml` (root chat-system)

```yaml
services:
  - type: web
    name: mcp
    runtime: docker
    plan: free            # 750h/mo, sleep 15min idle, cold start ~30s
    region: singapore
    branch: ft/imp-fe     # auto-deploy on push
    autoDeploy: true
    dockerfilePath: ./mcp/Dockerfile
    dockerContext: ./mcp
    healthCheckPath: /health
    # (Disk bỏ — Render free tier không hỗ trợ persistent disk)

    envVars:
      # Public config
      - key: APP_ENV
        value: production
      - key: DATABASE_URL
        value: sqlite+aiosqlite:////tmp/mcp.db   # ephemeral
      - key: GITHUB_OWNER
        value: cochecheee
      - key: GITHUB_REPO
        value: sample-python
      - key: POLLING_WORKFLOW_NAME
        value: Security
      - key: POLLING_INTERVAL_SECONDS
        value: "300"
      - key: POLLING_BRANCH
        value: main
      - key: GEMINI_MODEL
        value: gemini-2.5-flash
      - key: CORS_ORIGINS
        value: "http://localhost:5173,http://localhost:4173"

      # Secrets — set in Render UI (sync: false)
      - key: GITHUB_TOKEN
        sync: false
      - key: GEMINI_API_KEY
        sync: false
      - key: SECRET_KEY
        sync: false
      - key: CI_WEBHOOK_TOKEN
        sync: false
```

## Setup lần đầu (15 phút)

### 1. Render Dashboard
1. https://dashboard.render.com
2. **New + → Blueprint**
3. Connect GitHub → chọn `cochecheee/ChatSystem` → branch `ft/imp-fe`
4. Render đọc `render.yaml` → preview "1 Web Service, no disk"
5. **Apply** → Render build Docker image (lần đầu ~5-7 phút)

### 2. Set 4 secrets
Sau khi service tạo xong, vào **mcp service → Environment**:

| Key | Value | Lấy từ đâu |
|---|---|---|
| `GITHUB_TOKEN` | `github_pat_11A2ZM4HY0TH14...` | `mcp/.env` |
| `GEMINI_API_KEY` | `AIzaSyDk...` | `mcp/.env` |
| `SECRET_KEY` | 32+ random chars | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `CI_WEBHOOK_TOKEN` | 32+ random chars | Match với `MCP_WEBHOOK_TOKEN` ở sample-python secrets |

Save → Render auto-redeploy ~3 phút.

### 3. Set secrets ở sample-python
GitHub `cochecheee/sample-python` → Settings → Secrets → Actions:

| Key | Value |
|---|---|
| `MCP_GATEWAY_URL` | `https://mcp-l958.onrender.com` |
| `MCP_WEBHOOK_TOKEN` | Cùng giá trị với `CI_WEBHOOK_TOKEN` ở Render |

### 4. Tạo Project row trong mcp DB

```powershell
curl -X POST https://mcp-l958.onrender.com/projects `
  -H "Content-Type: application/json" `
  -d '{
    "name": "sample-python (sast-action demo)",
    "github_url": "https://github.com/cochecheee/sample-python",
    "github_owner": "cochecheee",
    "github_repo": "sample-python",
    "polling_workflow_name": "Security",
    "polling_branch": "main",
    "active": true
  }'
```

**Lưu ý**: Handler hiện chỉ persist `name + github_url` (legacy). Các field khác bị drop. Single-tenant runtime đọc từ env. Multi-tenant runtime ở v0.3.

## Redeploy workflow

```powershell
# Sửa code mcp
cd D:\School\DoAnTotNghiep\chat-system
git add mcp/
git commit -m "fix: ..."
git push origin ft/imp-fe

# → Render detect push → docker build → rollout container mới
# → ~3 phút sau live
```

URL không đổi. SQLite ở `/tmp/mcp.db` reset → webhook tự ingest lại trong vài phút.

## Lifecycle cold start

| Event | Hành động |
|---|---|
| Container active | Response ~200ms |
| 15 phút không có request | Container sleep |
| Request đầu sau sleep | Render boot container ~30-60s → client thấy timeout nếu timeout client < 60s |
| `curl -m 60 /health` | Hợp lý cho cold start lần đầu |
| `/health` keep-alive cron | Có thể setup external cron ping mỗi 10 phút để keep warm |

## Dashboard dev local

```powershell
cd D:\School\DoAnTotNghiep\chat-system\dashboard
# dashboard/.env.local đã point tới Render mcp:
#   VITE_API_URL=https://mcp-l958.onrender.com
npm run dev
# → http://localhost:5173 — fetch data từ Render mcp
```

CORS đã allow `localhost:5173` qua `CORS_ORIGINS` env.

## Upgrade options (khi cần persistence thật)

### A. Render Postgres free
- 90 ngày miễn phí, sau đó $7/mo
- Switch `DATABASE_URL=postgresql+asyncpg://...`
- Yêu cầu install `asyncpg` thay `aiosqlite` ở requirements
- Lợi: DB survives across redeploy, hỗ trợ concurrent writes

### B. Paid disk
- Render Starter $7/mo Web Service + $1/mo per GB disk
- Giữ SQLite, mount lại `/data`
- Restore `disk:` block trong render.yaml

### C. External SQLite + Litestream
- Chạy SQLite local + Litestream replicate to S3
- Restore on container start
- Phức tạp, không recommend cho thesis

## Multi-region notes

Render free tier hỗ trợ: oregon, frankfurt, ohio, singapore. Đang dùng singapore → latency VN ~50ms. Đổi region cần delete + recreate service.

---

## Staging service cho inheritor (V2.2)

Mỗi inheritor (sample-python, ALOUTE Java, ...) có 1 Render service riêng để host app sau khi CI pass.

### Setup lần đầu (10 phút)

#### 1. Docker Hub Access Token
- https://hub.docker.com → **Account Settings → Security → New Access Token**
- Name: `sast-action-ci`
- Permissions: **Read & Write**
- Copy token (chỉ hiện 1 lần) — lưu tạm

#### 2. Render service từ Docker image
- https://dashboard.render.com → **New + → Web Service**
- Source type: **Deploy an existing image from a registry**
- Image URL: `docker.io/cochecheee/sample-python:latest` (thay tên repo theo inheritor)
- Name: `sample-python` (sẽ thành subdomain `sample-python-XXX.onrender.com`)
- Plan: **Free**
- Region: Singapore
- Health check path: `/health` (sample-python có endpoint này)
- Port: `5000` (Flask default)
- Create Web Service → Render kéo image lần đầu

#### 3. Lấy Deploy Hook URL
- Service vừa tạo → **Settings → Deploy Hook**
- Render generate URL dạng: `https://api.render.com/deploy/srv-xxxxx?key=yyyyy`
- Copy URL — không share public (đây là webhook trigger redeploy)

#### 4. Add 3 secret vào inheritor GitHub repo
- https://github.com/cochecheee/sample-python/settings/secrets/actions

| Secret | Value |
|---|---|
| `DOCKER_USERNAME` | `cochecheee` |
| `DOCKER_PASSWORD` | Docker Hub Access Token (từ bước 1) |
| `RENDER_DEPLOY_HOOK` | URL từ bước 3 |

#### 5. Trigger CI
```powershell
cd D:\School\DoAnTotNghiep\sample-python
git commit --allow-empty -m "ci: trigger V2.2 CD"
git push
```

→ CI chạy ~5-7 phút (SAST 3 phút + build/push image 2 phút + Render pull image 1 phút).

### Verify
```powershell
# 1. CI job 'cd' phải ✅ ở github.com/cochecheee/sample-python/actions
# 2. Image xuất hiện ở https://hub.docker.com/r/cochecheee/sample-python/tags
# 3. App live:
curl https://sample-python-XXX.onrender.com/health
# {"status":"ok"}

# 4. Vuln endpoint demo (lưu ý: app này CỐ Ý vulnerable)
curl "https://sample-python-XXX.onrender.com/user?id=1' OR '1'='1"
```

### CI flow visualization

```
git push → GitHub Actions:
  ┌─ sast: ──────────────────────────────────────┐
  │  Semgrep + Trivy + Bandit + Safety (~3 phút) │
  │  Notify chat-system dashboard                │
  └───────────────────────────────────────────────┘
                       ↓ needs: sast
  ┌─ cd: ────────────────────────────────────────┐
  │  docker login                                │
  │  docker buildx build → load local            │
  │  Trivy scan image → SARIF artifact           │
  │  docker push :<sha> + :latest (~2 phút)      │
  │  POST Render Deploy Hook URL                 │
  └───────────────────────────────────────────────┘
                       ↓
  Render pulls cochecheee/sample-python:latest
  → app live ~1 phút sau push hook
```

### Cost (free tier)

- Render Web Service free: 750h/mo per service
- Có chat-system mcp + sample-python staging = 2 service = 1500h/mo
- 1 service ngủ 15 phút idle → cold start ~30s lần đầu request
- Docker Hub: unlimited public repos free
- GitHub Actions: 2000 phút/mo free cho personal account

→ V2.2 hoàn toàn $0/mo cho thesis demo.

# Biến môi trường — Local vs Render

> Bảng đầy đủ env vars của chat-system. Cột "Local" = `mcp/.env`, "Render" =
> Render Dashboard env vars (hoặc auto-inject từ `render.yaml`).
>
> Legend:
> - ✅ **bắt buộc** — không có thì sẽ fail
> - ⚠️ **bắt buộc khi prod** — local có thể bỏ trống
> - 🟡 **optional** — có default sensible, set khi cần override
> - ⛔ **không cần** — môi trường đó không dùng

---

## 1. Backend (MCP Gateway)

### 1.1 Database

| Biến | Local | Render | Dùng để làm gì |
|------|-------|--------|----------------|
| `DATABASE_URL` | ✅ | ✅ (auto từ `fromDatabase`) | Connection string SQLAlchemy. Local: `mysql+asyncmy://root:@127.0.0.1:3306/chat_system?charset=utf8mb4` (XAMPP MariaDB). Render: `postgres://...` auto-inject từ `mcp-db` blueprint → `core/config.py:_normalize_database_url` rewrite thành `postgresql+asyncpg://`. |

### 1.2 App identity & safety

| Biến | Local | Render | Dùng để làm gì |
|------|-------|--------|----------------|
| `APP_ENV` | 🟡 (`development`/`production`) | ✅ `production` | Quyết định behavior: dev mode bật echo SQL + CORS wildcard + skip production safety guard. Prod mode tắt echo, enforce strict CORS, fail-fast nếu missing secrets. |
| `SECRET_KEY` | ⚠️ (default `change-me-...`) | ✅ secret | HMAC key ký JWT (`python-jose` HS256). Default value bị reject bởi `_enforce_production_safety()` khi `APP_ENV=production`. Generate: `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 🟡 (default 480) | 🟡 | JWT TTL phút. Default 8 giờ. |
| `CORS_ORIGINS` | 🟡 (empty = wildcard `*` ở dev) | ✅ `https://dashboard-zyy0.onrender.com,http://localhost:5173,...` | Comma-separated origin list FE được phép call BE. Prod **không** chấp nhận `*` + `allow_credentials=true` cùng lúc (browser reject). |

### 1.3 GitHub integration

| Biến | Local | Render | Dùng để làm gì |
|------|-------|--------|----------------|
| `GITHUB_TOKEN` | ✅ | ✅ secret | Personal Access Token, scope `repo` + `workflow`. Dùng cho `GitHubClient.list_workflow_runs`, `fetch_artifact`, `dispatch_workflow`, `rerun_workflow`, `fetch_file_content`. Fallback khi project chưa có per-project credentials (V2.8 multi-tenant). |
| `GITHUB_OWNER` | ✅ | ✅ `cochecheee` | Owner GitHub (user/org) của repo target. Single-tenant ingest path đọc từ đây. |
| `GITHUB_REPO` | ✅ | ✅ `sample-python` | Tên repo target. Cùng `GITHUB_OWNER` tạo URL `https://github.com/{owner}/{repo}`. |

### 1.4 Polling (background task)

| Biến | Local | Render | Dùng để làm gì |
|------|-------|--------|----------------|
| `POLLING_INTERVAL_SECONDS` | 🟡 (default 300) | 🟡 `300` | Tần suất poller pull GitHub Actions runs mới. 300s = 5 phút. Lifespan task ở `main.py:78`. |
| `POLLING_WORKFLOW_NAME` | 🟡 (default `CI Workflow`) | ✅ `Security` | Tên workflow YAML cần poll. Phải khớp `name:` trong `.github/workflows/*.yml` của repo target. |
| `POLLING_BRANCH` | 🟡 (default `main`) | 🟡 `main` | Branch filter khi list workflow runs. |

### 1.5 AI (Gemini)

| Biến | Local | Render | Dùng để làm gì |
|------|-------|--------|----------------|
| `GEMINI_API_KEY` | ⚠️ | ✅ secret | Google AI API key. Empty → `/explain`, `/findings/triage`, `/findings/ai-summary` đều fail 503. Local có thể fake key để test path không gọi Gemini. |
| `GEMINI_MODEL` | 🟡 (default `gemini-2.5-flash`) | 🟡 `gemini-2.5-flash` | Model ID. `flash` cheap + fast cho thesis scope; có thể bump `gemini-2.5-pro` nếu cần chất lượng analysis. |
| `GEMINI_MAX_RETRIES` | 🟡 (default 3) | 🟡 `3` | Retry exponential backoff cho 429/503. |

### 1.6 CI ingest (webhook + artifacts API)

| Biến | Local | Render | Dùng để làm gì |
|------|-------|--------|----------------|
| `CI_API_KEY` | 🟡 (empty = auth disabled) | 🟡 `""` | Required header `X-API-Key` cho `POST /artifacts/process`. Empty → bypass auth (dev mode). |
| `CI_WEBHOOK_TOKEN` | ⚠️ (empty = auth disabled) | ✅ secret | Required header `Authorization: Bearer <token>` cho `POST /webhook/pipeline-complete`. Cũng accept làm bearer alternative cho `/findings/gate-count` (CI runner gọi gate check không cần JWT). |

### 1.7 Multi-tenant + RBAC kill-switches

| Biến | Local | Render | Dùng để làm gì |
|------|-------|--------|----------------|
| `MULTI_TENANT_ENABLED` | 🟡 (default `false`) | 🟡 `false`/`true` | Bật `true` để webhook route theo `payload.repository` field (V2.8). Poller iterate active projects parallel. False → fallback env `GITHUB_OWNER/REPO`. |
| `RBAC_PER_PROJECT` | 🟡 (default `false`) | 🟡 | Bật `true` để mọi project-scoped endpoint check `ProjectMember`. JWT mang `memberships` snapshot. Global `admin` bypass. |
| `ANONYMOUS_READ_ENABLED` | 🟡 (default `false` = secure) | 🟡 `false` | V3.3 kill-switch. `true` = bypass JWT cho read endpoints (legacy V2.x). `false` (mặc định) = mọi read cần JWT. |
| `FERNET_KEY` | 🟡 (empty) | 🟡 | Khi set → encrypt-at-rest `github_token`/`gemini_api_key`/`webhook_token` trong DB. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Thesis scope hiện để empty (plaintext). |

### 1.8 Monitor + Alert (V2.4)

| Biến | Local | Render | Dùng để làm gì |
|------|-------|--------|----------------|
| `MONITOR_ENABLED` | 🟡 (default `false`) | 🟡 `true` | Bật lifespan task `monitor_loop` + `prune_loop`. Ping uptime targets + raise Alert khi down. |
| `MONITOR_INTERVAL_SECONDS` | 🟡 (default 300) | 🟡 `300` | Tần suất ping mỗi target. |
| `MONITOR_TARGETS` | 🟡 (empty) | 🟡 `1:https://sample-python-latest.onrender.com/health` | Format `<project_id>:<url>,<project_id>:<url>,...`. URL được ping 2xx/3xx = up. |
| `MONITOR_DOWN_THRESHOLD` | 🟡 (default 2) | 🟡 `2` | Số fail liên tiếp trước khi raise Alert. |

### 1.9 SMTP (alert email)

| Biến | Local | Render | Dùng để làm gì |
|------|-------|--------|----------------|
| `SMTP_HOST` | ⛔ | 🟡 | SMTP server. Trống → email tắt, monitor vẫn raise Alert row trong DB. |
| `SMTP_PORT` | ⛔ | 🟡 (default 587) | — |
| `SMTP_USER` | ⛔ | 🟡 | — |
| `SMTP_PASS` | ⛔ | 🟡 secret | — |
| `SMTP_USE_TLS` | ⛔ | 🟡 (default true) | — |
| `EMAIL_FROM` | ⛔ | 🟡 | Sender address |
| `EMAIL_TO` | ⛔ | 🟡 | Comma-separated recipient list |

### 1.10 Observability

| Biến | Local | Render | Dùng để làm gì |
|------|-------|--------|----------------|
| `SENTRY_DSN` | ⛔ (default empty) | 🟡 | Khi set → `sentry_sdk.init()` ở lifespan, gửi exception + 10% trace sample. Empty → skip init, log warning. |

### 1.11 Test-only

| Biến | Local | Render | Dùng để làm gì |
|------|-------|--------|----------------|
| `TEST_MODE` | ⛔ | ⛔ | Set `1` → SQLite in-memory + bypass Gemini/GitHub + expose `/test/reset` + `/test/inject-finding`. Playwright E2E dùng. Không bao giờ set trong dev/prod. |
| `SKIP_ALEMBIC` | ⛔ | ⛔ | Set `1` → `init_db()` skip `_run_alembic_upgrade()`. Test conftest dùng vì test DB là SQLite in-memory recreated mỗi test. |
| `INIT_DB_DROP_ALL` | ⛔ | ⛔ | Set `1` → `init_db()` drop+recreate tất cả bảng. Emergency reset, dữ liệu mất. |

---

## 2. Frontend (Dashboard)

`dashboard/.env.local` (cho dev) hoặc env vars trong Render Static Site:

| Biến | Local | Render | Dùng để làm gì |
|------|-------|--------|----------------|
| `VITE_API_URL` | ✅ `http://localhost:8000` | ✅ `https://mcp-l958.onrender.com` | Base URL FE gọi BE. `api/client.ts:3` đọc qua `import.meta.env.VITE_API_URL`. **Phải set khi build** vì Vite inline value vào bundle (không runtime read). |

---

## 3. File `.env` example cho LOCAL

```ini
# Database — XAMPP MariaDB port 3306 (XAMPP Apache ở port 8888 là URL phpMyAdmin)
DATABASE_URL=mysql+asyncmy://root:@127.0.0.1:3306/chat_system?charset=utf8mb4

# App identity
APP_ENV=production    # production = tắt echo SQL; cần fill 3 biến dưới đây
SECRET_KEY=<32-byte hex>
ACCESS_TOKEN_EXPIRE_MINUTES=480
CORS_ORIGINS=http://localhost:5173,http://localhost:4173

# GitHub
GITHUB_TOKEN=ghp_xxx
GITHUB_OWNER=cochecheee
GITHUB_REPO=sample-python

# Polling
POLLING_INTERVAL_SECONDS=300
POLLING_WORKFLOW_NAME=CI Workflow
POLLING_BRANCH=main

# Gemini
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-2.5-flash
GEMINI_MAX_RETRIES=3

# CI ingest
CI_API_KEY=
CI_WEBHOOK_TOKEN=local-dev-webhook-token

# Flags — false cho dev đơn giản
MULTI_TENANT_ENABLED=false
RBAC_PER_PROJECT=false
ANONYMOUS_READ_ENABLED=true     # true = cho local dev không cần JWT mỗi request
FERNET_KEY=

# Monitor + SMTP + Sentry — off local
MONITOR_ENABLED=false
SENTRY_DSN=
```

---

## 4. Render env vars (Dashboard → mcp service → Environment)

Phần lớn đã hardcoded trong `render.yaml`. Chỉ 4 secret cần fill thủ công ở Render UI:

| Secret (sync: false trong render.yaml) | Dùng để làm gì |
|----------------------------------------|----------------|
| `GITHUB_TOKEN` | PAT scope repo+workflow để poll + fetch artifacts |
| `GEMINI_API_KEY` | Google AI API key |
| `SECRET_KEY` | JWT signing — random 32-byte hex |
| `CI_WEBHOOK_TOKEN` | Shared secret với GitHub Actions step gọi webhook |

Còn lại Render tự inject (`DATABASE_URL` từ Postgres blueprint) hoặc cố định trong YAML.

---

## 5. Generate values nhanh (Windows PowerShell)

```powershell
# SECRET_KEY (32 bytes hex)
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"

# CI_WEBHOOK_TOKEN (URL-safe random)
.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"

# FERNET_KEY (32 bytes base64)
.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

⚠️ Lệnh trên gõ bằng **double quotes** `"` quanh Python expression. Single quotes `'` sẽ fail trên PowerShell vì variable substitution.

---

## 6. Nhanh cheatsheet: muốn làm X cần biến nào

| Mục đích | Biến cần set |
|----------|--------------|
| Backend khởi động được | `DATABASE_URL` |
| Backend prod-mode pass safety guard | `SECRET_KEY`, `CI_WEBHOOK_TOKEN`, `CORS_ORIGINS` (non-default) |
| GitHub poller hoạt động | `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO`, `POLLING_*` |
| AI features (/explain, /triage, /ai-summary) | `GEMINI_API_KEY` |
| CI gửi webhook → ingest | `CI_WEBHOOK_TOKEN` (cả 2 phía: chat-system + sast-action) |
| Security Gate trong CI | `CI_WEBHOOK_TOKEN` (CI runner dùng làm bearer cho `/findings/gate-count`) |
| Multi-tenant routing | `MULTI_TENANT_ENABLED=true` + per-project credentials trong DB |
| Per-project RBAC | `RBAC_PER_PROJECT=true` + ProjectMember rows |
| Uptime monitor + alert | `MONITOR_ENABLED=true`, `MONITOR_TARGETS`, SMTP_* |
| Encrypted credentials | `FERNET_KEY` |
| Sentry error tracking | `SENTRY_DSN` |
| FE connect tới đúng BE | `VITE_API_URL` (dashboard/.env.local hoặc Render Static env) |

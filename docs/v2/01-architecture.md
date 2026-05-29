# 01 — Kiến trúc tổng thể

## 1.1 Component map

```
┌────────────────────────────────────────────────────────────────────┐
│                  External world (GitHub + Gemini)                  │
└─────────────┬───────────────────────────────────────┬──────────────┘
              │                                       │
       GitHub Actions API                       Gemini API
       (Actions runs, artifacts ZIP,            (structured output JSON,
        workflow dispatch, rerun)                tiếng Việt)
              │                                       │
              │                                       │
     ┌────────▼───────────────────────────────────────▼────────┐
     │              MCP Gateway (FastAPI, Python 3.13)         │
     │                                                         │
     │   ┌────────────────┐  ┌──────────────────────────────┐  │
     │   │   API layer    │  │      Background tasks        │  │
     │   │ api/            │  │  - GitHubPoller (5 min)      │  │
     │   │   artifacts.py  │  │  - monitor_loop (uptime)     │  │
     │   │   analysis.py   │  │  - prune_loop (daily)        │  │
     │   │   chat.py       │  └──────────────────────────────┘  │
     │   │   stats.py      │                                    │
     │   │   monitor.py    │  ┌──────────────────────────────┐  │
     │   │   config.py     │  │      Service layer            │  │
     │   └───────┬────────┘  │  services/                    │  │
     │           │           │   processor.py  (orchestrator) │  │
     │           │           │   normalizer.py (6 parsers)    │  │
     │           ▼           │   enricher.py   (CWE/CVSS)     │  │
     │   ┌────────────────┐  │   github_client.py             │  │
     │   │  Repository   │  │   poller.py                    │  │
     │   │  repositories/│  │   command_service.py (ChatOps) │  │
     │   │   finding_repo│  │   report_service.py            │  │
     │   │   project_repo│  │   stats_service.py             │  │
     │   │   ...         │  │   llm/  (Gemini integration)   │  │
     │   └───────┬────────┘  └──────────────────────────────┘  │
     │           │                                              │
     │           ▼                                              │
     │   ┌──────────────────┐                                  │
     │   │  SQLAlchemy 2.0  │ async, aiosqlite / asyncpg       │
     │   │  models/         │                                  │
     │   └────────┬─────────┘                                  │
     │            │                                            │
     └────────────┼────────────────────────────────────────────┘
                  │
         ┌────────▼────────┐
         │  SQLite (dev)   │
         │  Postgres (prod)│ ← Render managed
         └─────────────────┘

     ┌────────────────────────────────────────────────────────┐
     │            Dashboard (React 19 + Vite + TS)            │
     │                                                        │
     │   App.tsx — router (switch active page)                │
     │     AuthProvider — JWT in localStorage                 │
     │     ProjectProvider — activeProjectId selector         │
     │                                                        │
     │   pages/                                               │
     │     Overview · Pipelines · Vulns · Sca · Runtime ·     │
     │     Monitor · Chat · Reports · Settings                │
     │                                                        │
     │   api/client.ts — typed fetch wrappers, 401 handler    │
     │   features/ — auth, findings/useStats, pipelines/useRuns│
     │   components/ — Shell · Charts · OverviewAiSummary ·   │
     │     AiTriageModal · ProjectMembers · ProjectSuppressions│
     └────────────────────────────────────────────────────────┘
```

## 1.2 Deployment topology

| Env | Backend | Frontend | DB | Notes |
|-----|---------|----------|----|-------|
| **local dev** | `uvicorn src.main:app --reload --port 8000` | `npm run dev` (Vite @ 5173) | SQLite file `mcp.db` | `APP_ENV=development`, CORS=`*` |
| **Docker** | `docker-compose.yml` build từ `./mcp` | nginx serve `dist/` | SQLite in named volume `mcp_data` | nginx proxy `/docs` → mcp |
| **Render (prod)** | Free web service, FastAPI | Static site Render | Postgres free 256MB | `APP_ENV=production`, fail-fast nếu config thiếu |

### Domain hiện tại (theo memory)
- MCP API: `https://mcp-l958.onrender.com`
- Dashboard: `https://dashboard-zyy0.onrender.com`

Cả 2 cùng repo → `render.yaml` định nghĩa 2 service + 1 Postgres add-on.

## 1.3 Lịch sử các phiên bản (V-stack)

Repo đã chồng các phiên bản incremental. Mỗi feature mới gắn comment `V2.8`,
`V3.1 Tier 2`, ... — đọc comment trong source để biết tại sao có code đó.

| Version | Chốt được gì |
|---------|--------------|
| **V2.x** | Single-tenant ingest, JWT demo login, ChatOps 7 lệnh, Playwright E2E. |
| **V2.4** | Monitor + alert (UptimeCheck, Alert, SMTP). |
| **V2.7** | Per-field PII scrub (fix bug JSON SARIF bị break do regex ăn vào escape). |
| **V2.8** | Multi-tenant runtime (`MULTI_TENANT_ENABLED`). Webhook route theo `payload.repository`; poller iterate active projects parallel. Per-project Gemini + GitHub credentials. |
| **V2.9** | Stats endpoints accept `?project_id=`. |
| **V3.0** | Per-project RBAC (`RBAC_PER_PROJECT`). `ProjectMember` table; JWT mang snapshot `memberships`. |
| **V3.1 Tier 1** | Cross-run auto-revoke theo `dedup_hash` đã từng REVOKED. |
| **V3.1 Tier 2** | `SuppressionRule` pattern-based (rule_id/file_glob/tool/severity). |
| **V3.1 Tier 3** | AI batch triage `/findings/triage` qua Gemini. |
| **V3.1 Tier 4** | Security Gate qua `/findings/gate-count`. |
| **V3.2** | Quality pass: `enforce_finding_project_access`, eager-load Artifact để tránh `MissingGreenlet`. |
| **V3.3** | Auth hardening: `ANONYMOUS_READ_ENABLED=false` mặc định → mọi read cần JWT. Kill-switch để rollback. |
| **V3.3.B** | Overview AI summary card (Gemini structured output 4-section, cache 10 phút). |
| **V3.4** | Summary accuracy — real GitHub pass rate, diverse risks, active counts. Severity normalizer correctness sweep. |

## 1.4 Feature flags (kill-switches)

Tất cả nằm trong `core/config.py` (`Settings`). Bật/tắt qua env không cần redeploy code:

| Flag | Default | Tác dụng |
|------|---------|---------|
| `MULTI_TENANT_ENABLED` | `false` | Webhook lookup project theo `repository` field; poller iterate all active projects. |
| `RBAC_PER_PROJECT` | `false` | Bật check `ProjectMember` ở mọi endpoint project-scoped. Global `admin` vẫn bypass. |
| `ANONYMOUS_READ_ENABLED` | `false` (V3.3 secure) | Cho phép anonymous đọc các endpoint `/findings`, `/stats`, `/projects`. Để `true` chỉ khi rollback khẩn cấp. |
| `MONITOR_ENABLED` | `false` | Bật `monitor_loop` + `prune_loop` lifespan task. |
| `FERNET_KEY` | empty | Khi set → mã hoá `github_token`/`gemini_api_key` at rest (chưa fully wired, decision: plaintext trong thesis scope). |
| `CI_API_KEY` | empty | Empty = auth disabled cho `/artifacts/process`. |
| `CI_WEBHOOK_TOKEN` | empty | Empty = auth disabled cho `/webhook/pipeline-complete`. Cũng được CI dùng làm bearer cho `/findings/gate-count`. |

`_enforce_production_safety()` trong `main.py:33` refuse start nếu
`APP_ENV=production` mà `SECRET_KEY`/`CI_WEBHOOK_TOKEN`/`CORS_ORIGINS` rỗng.

## 1.5 Tech stack chi tiết

### Backend
- **Runtime**: Python 3.13, `uvicorn[standard]`
- **Framework**: FastAPI + Pydantic v2 (`pydantic-settings` cho config từ env)
- **ORM**: SQLAlchemy 2.0 async style (`mapped_column`, `AsyncSession`)
- **DB driver**: `aiosqlite` (dev), `asyncpg` (prod). `core/config.py:_normalize_database_url` rewrite `postgres://` → `postgresql+asyncpg://` cho Render.
- **Auth**: `python-jose` HS256 JWT (`core/auth.py`). Bearer in `Authorization` header.
- **AI**: `google-genai` SDK với `response_schema=` Pydantic structured output.
- **Security libs**: `detect-secrets` (line-level secret scrubbing), `defusedxml` (SpotBugs XML parser), regex cho PII (email, IPv4).
- **Rate limit**: `slowapi` (chỉ wrap `/findings/{id}/explain`).
- **Observability**: `sentry-sdk` opt-in qua `SENTRY_DSN`.

### Frontend
- **Framework**: React 19, TypeScript 6, Vite 8
- **State**: React context (AuthContext, ProjectContext) + local `useState`. Không Redux/Zustand.
- **Polling**: `useInterval` pattern qua `setInterval` trong `useEffect`. `POLL_INTERVAL_MS` từ `lib/constants.ts`.
- **HTTP**: `fetch` thuần, wrap trong `api/client.ts`. Type-safe vì manual TS interface trong `types/`.
- **UI primitives**: Sonner toast, SVG charts inline (`components/Charts.tsx`), inline SVG icon library (`components/Icon.tsx`). Không component framework.
- **CSS**: `tokens.css` design-system variables + module CSS scoped per page.
- **E2E**: Playwright (`tests/e2e/`).

## 1.6 Tại sao kiến trúc trông như thế này

| Design choice | Lý do |
|---------------|------|
| Async toàn bộ backend | I/O-bound (GitHub + Gemini + DB) → asyncio đơn giản nhất; SQLAlchemy 2.0 async ổn rồi. |
| Background task qua `asyncio.create_task` trong lifespan | Free tier Render không có queue worker; chấp nhận task chết nếu instance restart. Webhook luôn 202 ngay để CI không timeout. |
| SQLite dev / Postgres prod cùng codebase | `DT_TZ` (tz-aware DateTime) cho asyncpg, SQLite ignore — code không phải branch. |
| Per-field PII scrub thay vì pre-parse | Pre-parse regex ăn vào JSON escape (`\\n@app` → `\\[EMAIL_SCRUBBED]` → invalid escape) → break SARIF lớn. Xem `core/guardrails.py:scrub_content`. |
| Membership snapshot trong JWT | Tránh hit DB mỗi request kiểm tra role. Trade-off: token cần invalidate khi đổi membership (hiện không có blacklist; chấp nhận TTL 480 phút). |
| Cache AI summary in-memory 10 phút | Gemini quota free 60 req/min; Overview page polling 30s → cache reset thrash. |
| No queue, no celery | Solo dev thesis; tăng complexity không justify được. |

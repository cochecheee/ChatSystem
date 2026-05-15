# 02 — Kiến trúc

## 3-Repo Topology

```
┌─────────────────────────────────────────────────────────────────┐
│ REPO 1: cochecheee/ChatSystem                                   │
│  D:\School\DoAnTotNghiep\chat-system                            │
│                                                                  │
│  mcp/        FastAPI backend (deploy Render)                    │
│  dashboard/  React frontend (dev local, deploy V2.5)            │
│  docs/       inheritor-guide, demo, project-docs                │
│  render.yaml Blueprint cho Render                                │
│                                                                  │
│  Branch: ft/imp-fe                                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ REPO 2: cochecheee/sast-action  (reusable GitHub Actions lib)   │
│  D:\School\DoAnTotNghiep\sast-action                            │
│                                                                  │
│  action.yml                       Legacy v0.1.0 notify-only      │
│  actions/notify-dashboard/        Composite: POST webhook        │
│  actions/sast-suite/              Composite: chạy SAST per lang  │
│  actions/aggregate-sarif/         Composite: gom SARIF (V2+)     │
│  .github/workflows/sast-ci.yml    Reusable workflow              │
│                                                                  │
│  Branch: master                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ REPO 3: cochecheee/sample-python  (inheritor demo)              │
│  D:\School\DoAnTotNghiep\sample-python                          │
│                                                                  │
│  app.py             Flask vulnerable: 5 lỗ hổng cố ý             │
│  requirements.txt   Flask==1.0 (CVE-có-chủ-đích)                 │
│  Dockerfile         Container build cho V2.2 CD                  │
│  .github/workflows/security.yml  10 dòng `uses:` reusable wf     │
│                                                                  │
│  Branch: main                                                    │
└─────────────────────────────────────────────────────────────────┘
```

## Vai trò

| Repo | Role | Đối tượng dùng |
|---|---|---|
| **ChatSystem** | Hệ điều hành — backend nhận webhook, dashboard hiển thị | Security_lead, Dev (xem AI fix) |
| **sast-action** | Thư viện — composite action + reusable workflow | Bất kỳ project nào muốn có SAST |
| **sample-python** | Demo — inheritor reference cho thesis | Defense demo, template clone |

## Cấu trúc chat-system (chi tiết)

```
chat-system/
├── mcp/                          Backend
│   ├── src/
│   │   ├── api/                  Route handlers (artifacts, chat, stats, config, analysis)
│   │   ├── core/                 Config, DB, auth, guardrails, profiles
│   │   ├── models/               SQLAlchemy entities + Pydantic schemas
│   │   ├── repositories/         DB query layer
│   │   ├── services/             Business logic
│   │   │   ├── llm/              Gemini client, prompts, schemas
│   │   │   ├── processor.py      SARIF ingest + normalize
│   │   │   ├── normalizer.py     SARIF → Finding mapping
│   │   │   ├── poller.py         GitHub API fallback polling
│   │   │   ├── github_client.py  GitHub PR/file fetch
│   │   │   └── stats_service.py  KPI aggregation
│   │   └── main.py               FastAPI app, CORS, lifespan
│   ├── config/profiles/          Artifact-name profile YAML
│   ├── scripts/                  migrate_v2, reset_db, smoke_test, lint_workflows
│   ├── tests/                    200 pytest cases
│   ├── Dockerfile                Multi-stage Python 3.13-slim, non-root
│   └── requirements.txt
│
├── dashboard/                    Frontend
│   ├── src/
│   │   ├── api/client.ts         Fetch wrapper, VITE_API_URL base
│   │   ├── components/           Shell, Sidebar, design system primitives
│   │   ├── pages/                Overview, Pipelines, Vulns, Sca, Chat, Reports
│   │   ├── hooks/                useAuth, useAppConfig
│   │   └── types.ts              TypeScript shapes
│   ├── nginx.conf                Production reverse proxy (same-origin)
│   ├── Dockerfile                Build → nginx serve
│   ├── .env.local                VITE_API_URL=https://mcp-l958.onrender.com (gitignored)
│   └── package.json
│
├── docs/                         Documentation
│   ├── project/                  ← Bạn đang ở đây
│   ├── demo-script.md            15' demo flow
│   ├── inheritor-guide.md        5' onboard 1 inheritor mới
│   ├── webhook-schema.md         JSON shape của /webhook/pipeline-complete
│   ├── guardrails.md             24 AI safety tests
│   ├── actions-testing.md        Level 1/2/3 test GitHub Actions
│   ├── testing.md                Comprehensive testing guide
│   ├── preflight-checklist.md    Pre-defense checklist
│   ├── troubleshooting.md        Bug → fix recipe
│   ├── release-notes-v0.1.0.md   Changelog v0.1
│   └── slide-outline.md          Defense slide structure
│
├── .planning/                    Planning artifacts (per-session)
│   └── redesign/
│       ├── ANALYSIS.md, REDUNDANCY.md, REUSABILITY.md
│       ├── PHASE-V2.md, PROGRESS.md, NEXT-PHASES.md
│       ├── PLAN-1WEEK.md, OPEN-QUESTIONS.md
│
├── docker-compose.yml            Local stack
├── docker-compose.example.yml    Pull Docker Hub image
├── render.yaml                   Render Blueprint
├── start.bat, stop.bat, dev.bat  Windows launcher
├── CHANGELOG.md                  Keep-a-Changelog
└── README.md
```

## Cái "mcp" — dual protocol từ V2.7

Folder `mcp/` host 2 process độc lập, cùng codebase + DB:

| Protocol | Entry point | Client | Mục đích |
|---|---|---|---|
| **REST HTTP** (FastAPI) | `uvicorn src.main:app` | React dashboard, curl, CI webhook | UI + integration |
| **Anthropic MCP** | `python -m src.mcp_server` | Claude Desktop, Cursor, MCP Inspector | AI agent natural-language access |

MCP server (`mcp/src/mcp_server.py`) — dùng `fastmcp` SDK, expose 8 tool wrap repositories + services. Mỗi tool dùng `AsyncSessionLocal` chia sẻ với FastAPI process → cùng `mcp.db` hoặc Render Postgres.

Xem [`docs/mcp-server.md`](../mcp-server.md) cho config Claude Desktop + 8 tool reference.

**Lý do "dual protocol"**:
- REST cần cho dashboard React (browser fetch) + CI webhook (curl). MCP transport stdio/SSE không phù hợp browser direct.
- MCP cần cho AI agent (Claude Desktop) — REST tích hợp được nhưng cần wrapper. Anthropic MCP chuẩn hoá → connect 1 lần, dùng nhiều agent.

Khi nói "MCP Server" trong báo cáo (ch.3.2 + ch.4.1) → reference Anthropic MCP. Khi nói "MCP Gateway" trong code path `mcp/src/api/` (REST) → reference middleware role giữa CI/CD và LLM (terminology cũ giữ vì có nhiều inheritor + URL `mcp-l958.onrender.com` đã chạy production).

## Component data ownership

```
GitHub API   ─────► mcp/poller.py        ─┐
                                          ├─► Artifact rows  ─► SARIF parse
GitHub webhook ─► mcp/api/webhook        ─┘                       │
                                                                  ▼
                                          Finding rows  ◄─── Normalizer
                                              │
                                              ▼
                                          AI analysis (lazy, on demand)
                                              │  Gemini API
                                              ▼
                                          AnalysisCache JSON
                                              │
                                              ▼
                                          Dashboard fetch
```

## Multi-tenant scaffolding

`Project` entity có 9 cột (name, github_url, github_owner, github_repo, github_token, gemini_api_key, gemini_model, artifact_profile, polling_workflow_name, polling_branch, active, last_processed_run_id) — sẵn cho multi-tenant.

**Runtime hiện tại vẫn single-tenant**: poller + processor đọc `GITHUB_OWNER`/`GITHUB_REPO` từ env. Per-project credentials sẽ wire khi Fernet encryption ready (v0.3).

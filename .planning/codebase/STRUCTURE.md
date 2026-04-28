# Codebase Structure

**Analysis Date:** 2026-04-28

## Root Layout

```
chat-system/
├── mcp/                  # Backend — MCP Gateway Server (Python/FastAPI)
├── dashboard/            # Frontend — React Web Dashboard (TypeScript/Vite)
├── images/               # Screenshot assets for README
├── .planning/            # GSD planning documents
├── .claude/              # Claude Code workspace config
├── README.md             # Project overview, setup guide, API reference
├── run.txt               # Developer convenience: local startup commands
└── .gitignore
```

## Service Layouts

### mcp/ — Backend (FastAPI)

```
mcp/
├── src/
│   ├── main.py               # FastAPI app, router registration, lifespan (DB + poller)
│   ├── api/
│   │   ├── artifacts.py      # Routers: /projects, /findings, /github/runs, /artifacts/process, /webhook
│   │   ├── analysis.py       # Router: POST /findings/{id}/explain (AI analysis, rate-limited)
│   │   └── chat.py           # Router: /api/chat/{command,message,report,auth/token}
│   ├── core/
│   │   ├── auth.py           # JWT HS256: create_access_token, get_current_user, User model
│   │   ├── config.py         # Pydantic Settings — loads from .env
│   │   ├── db.py             # SQLAlchemy async engine, AsyncSessionLocal, init_db, _migrate_schema
│   │   └── guardrails.py     # ScrubbingService (PII/secrets), InjectionGuardrail
│   ├── models/
│   │   ├── entities.py       # ORM: Project, Artifact, Finding (audit trail columns)
│   │   └── schemas.py        # Pydantic I/O: FindingCreate, FindingOut, CommandRequest/Response,
│   │                         #   AnalysisResult, TokenRequest/Response, WebhookRunPayload
│   └── services/
│       ├── processor.py      # SecurityProcessor: full artifact pipeline orchestrator
│       ├── poller.py         # GitHubPoller: asyncio background task
│       ├── normalizer.py     # NormalizerFactory + parsers: SARIF, SpotBugs XML, DepCheck, Trivy
│       ├── enricher.py       # DataEnricher: CWE/CVSS/OWASP Top 10 enrichment
│       ├── github_client.py  # GitHubClient: runs, artifacts, dispatch, rerun (httpx async)
│       ├── command_service.py # CommandService: handles 7 ChatOps slash commands
│       ├── report_service.py  # generate_html(): HTML report export
│       └── llm/
│           ├── client.py     # GeminiClient: analyze() + chat() with retry
│           ├── prompts.py    # build_prompt(), SYSTEM_INSTRUCTION, CHAT_SYSTEM_INSTRUCTION
│           ├── schemas.py    # AnalysisOutput (structured Gemini response schema)
│           └── service.py    # LLMAnalysisService: orchestrates finding analysis
├── tests/
│   ├── conftest.py
│   ├── test_normalizer.py
│   ├── test_enricher.py
│   ├── test_guardrails_scrubbing.py
│   ├── test_guardrails_injection.py
│   ├── test_processor.py
│   ├── test_poller.py
│   ├── test_chat_api.py
│   ├── test_api_integration.py
│   ├── test_llm_api.py
│   ├── test_llm_client.py
│   ├── test_llm_schemas.py
│   ├── test_llm_service.py
│   ├── test_github_client.py
│   ├── test_db.py
│   ├── test_e2e.py
│   ├── test_main.py
│   └── test_schemas.py
├── requirements.txt
├── .env                      # Local secrets (not committed)
├── .env.example              # Template for required env vars
├── mcp.db                    # SQLite database (generated at runtime)
└── .venv/                    # Python virtual environment (not committed)
```

### dashboard/ — Frontend (React + Vite)

```
dashboard/
├── src/
│   ├── main.tsx              # React root mount point
│   ├── App.tsx               # Root component: routing state, finding poll interval, theme
│   ├── App.css               # App-level styles
│   ├── index.css             # Global reset + base styles
│   ├── tokens.css            # Design system CSS variables (colors, spacing, typography)
│   ├── api/
│   │   └── client.ts         # Typed fetch wrapper: api.findings, api.github, api.chat, etc.
│   ├── components/
│   │   ├── Shell.tsx         # Sidebar + Topbar layout; defines PageId type and NAV config
│   │   ├── Charts.tsx        # SVG chart components: Sparkline, Donut, Heatmap, AreaTrend
│   │   ├── Icon.tsx          # Inline SVG icon library
│   │   └── modals/
│   │       ├── ApprovalDialog.tsx  # /approve confirmation dialog with justification input
│   │       ├── RevokeDialog.tsx    # /revoke confirmation dialog with justification input
│   │       └── ActionDialog.tsx    # Generic action confirmation dialog base
│   ├── pages/
│   │   ├── Overview.tsx      # KPI cards, severity distribution, pipeline heatmap, top rules
│   │   ├── Vulns.tsx         # Split-pane: findings list + detail + AI panel + audit trail
│   │   ├── Pipelines.tsx     # GitHub workflow runs list, per-run findings board, Reprocess
│   │   ├── Chat.tsx          # ChatOps: JWT login UI, slash command handling, free-form chat
│   │   ├── Reports.tsx       # HTML report download trigger
│   │   └── Settings.tsx      # App settings page
│   ├── types/
│   │   └── index.ts          # TypeScript interfaces: Finding, Project, WorkflowRun,
│   │                         #   WorkflowArtifact, AnalysisResult, CommandRequest/Response,
│   │                         #   TokenResponse, Severity, SEVERITY_ORDER
│   ├── utils/
│   │   └── toast.ts          # Sonner toast helpers: notify.newFindings, updateCritHighBaseline
│   └── assets/               # Static images (hero.png, react.svg, vite.svg)
├── public/                   # Vite public assets (favicon, etc.)
├── dist/                     # Vite build output (generated, not committed)
│   └── assets/
├── tests/e2e/                # Playwright E2E tests
│   ├── chatops.spec.ts
│   ├── approval.spec.ts
│   ├── report.spec.ts
│   └── polling.spec.ts
├── playwright.config.ts      # Playwright configuration
├── package.json
├── tsconfig.json
├── vite.config.ts
└── node_modules/             # npm dependencies (not committed)
```

## Shared Code

There is no shared library between frontend and backend. The two services define equivalent types independently:

- **Backend:** `mcp/src/models/schemas.py` — Pydantic models (Python)
- **Frontend:** `dashboard/src/types/index.ts` — TypeScript interfaces

These must be kept in sync manually when the API contract changes.

**Common utilities within the backend:**
- `mcp/src/models/schemas.py:compute_dedup_hash()` — used by both `normalizer.py` (dedup check) and `processor.py` (hash assignment before DB insert)
- `mcp/src/core/config.py:settings` — singleton imported throughout all backend modules

## Configuration Files

| File | Purpose |
|------|---------|
| `mcp/src/core/config.py` | Pydantic Settings class — all backend configuration with defaults |
| `mcp/.env` | Actual env vars (secrets); not committed |
| `mcp/.env.example` | Template listing all required env vars |
| `dashboard/vite.config.ts` | Vite build config; `VITE_API_URL` env var sets backend URL |
| `dashboard/tsconfig.json` | TypeScript compiler options |
| `dashboard/playwright.config.ts` | Playwright E2E test config |
| `dashboard/package.json` | Node deps, scripts: `dev`, `build`, `test:e2e`, `test:e2e:ui` |
| `mcp/requirements.txt` | Python dependencies |

**Critical env vars (see `mcp/src/core/config.py` for full list):**
- `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO` — GitHub API access
- `GEMINI_API_KEY` — Google Gemini
- `SECRET_KEY` — JWT signing key (min 32 chars)
- `DATABASE_URL` — defaults to `sqlite+aiosqlite:///./mcp.db`
- `APP_ENV` — `development` | `production` | `testing`

## Generated / Build Artifacts

| Path | Generated By | Committed |
|------|-------------|-----------|
| `mcp/mcp.db` | SQLite, created on first `uvicorn` startup via `init_db()` | No |
| `mcp/.venv/` | `python -m venv .venv` | No |
| `mcp/.pytest_cache/` | pytest | No |
| `dashboard/dist/` | `npm run build` (Vite) | No |
| `dashboard/node_modules/` | `npm install` | No |

## Naming Conventions

**Backend files:**
- `snake_case.py` for all Python modules
- Routers named `{domain}.py` under `mcp/src/api/`
- Services named by responsibility: `processor.py`, `poller.py`, `normalizer.py`, `enricher.py`

**Frontend files:**
- `PascalCase.tsx` for React components and pages
- `camelCase.ts` for utilities and API client
- `index.ts` for type definitions barrel
- Page components prefixed with `Page`: `PageOverview`, `PageVulns`, etc.

**Database:**
- Table names: plural snake_case (`projects`, `artifacts`, `findings`)
- Status values: lowercase string literals (`pending`, `processed`, `failed`, `pending_review`, `ai_analyzed`, `APPROVED`, `REVOKED`)

## Where to Add New Code

**New API endpoint:**
- Add route handler to relevant router in `mcp/src/api/` (or create new file and register in `mcp/src/main.py`)
- Add corresponding Pydantic request/response models to `mcp/src/models/schemas.py`
- Add TypeScript interface to `dashboard/src/types/index.ts`
- Add typed fetch method to `dashboard/src/api/client.ts`

**New SAST tool normalizer:**
- Add new `BaseNormalizer` subclass to `mcp/src/services/normalizer.py`
- Register filename pattern in `NormalizerFactory.get()` at the bottom of `mcp/src/services/normalizer.py`
- Add artifact name to `_SECURITY_ARTIFACT_NAMES` or `_SECURITY_ARTIFACT_PREFIXES` in `mcp/src/services/processor.py:21-32`
- Add test to `mcp/tests/test_normalizer.py`

**New ChatOps slash command:**
- Add handler method `_handle_{cmd}` to `CommandService` in `mcp/src/services/command_service.py`
- Register in `dispatch` dict in `CommandService.handle()`
- Add role requirements to `COMMAND_ROLES` dict in `mcp/src/api/chat.py:28`
- Add natural-language pattern to `_suggested_command()` in `mcp/src/api/chat.py:105`

**New Dashboard page:**
- Create `dashboard/src/pages/New{Name}.tsx`
- Add `PageId` type union value in `dashboard/src/components/Shell.tsx:3`
- Add nav entry to `NAV` array in `dashboard/src/components/Shell.tsx`
- Add CRUMB entry in `dashboard/src/components/Shell.tsx`
- Add case to switch in `dashboard/src/App.tsx:51`

**New shared utility (backend):**
- Helpers that are domain-specific belong in the relevant service file
- Truly cross-cutting helpers belong in `mcp/src/core/`

**New React component:**
- Presentational/shared: `dashboard/src/components/`
- Modal: `dashboard/src/components/modals/`
- Page-specific: keep inline in the page file unless reused

## Special Directories

**`.planning/`:**
- Purpose: GSD planning documents (phases, roadmap, codebase maps)
- Generated: By GSD tooling and human authors
- Committed: Yes

**`.claude/`:**
- Purpose: Claude Code workspace metadata
- Generated: By Claude Code
- Committed: Partially (worktrees config)

**`mcp/.pytest_cache/`:**
- Purpose: pytest result cache
- Generated: Yes (by pytest)
- Committed: No

**`images/`:**
- Purpose: Dashboard screenshots embedded in README.md
- Committed: Yes

---

*Structure analysis: 2026-04-28*

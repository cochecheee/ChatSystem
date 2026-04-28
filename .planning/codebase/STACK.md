# Technology Stack

**Analysis Date:** 2026-04-28

## Languages

**Primary:**
- Python 3.13 — Backend (MCP Gateway server, `mcp/`)
- TypeScript 6.0 — Frontend (React dashboard, `dashboard/src/`)

**Secondary:**
- HTML/CSS — Report generation (`mcp/src/services/report_service.py`) and design tokens (`dashboard/src/tokens.css`)

## Runtime

**Environment:**
- Python 3.13+ (required; venv at `mcp/.venv/`)
- Node.js 20+ (required for dashboard)

**Package Manager:**
- Backend: `pip` with `requirements.txt` (`mcp/requirements.txt`)
- Frontend: `npm` with `package.json` (`dashboard/package.json`)
- Lockfile: `dashboard/package-lock.json` (npm)

## Frameworks

**Core (Backend):**
- FastAPI (from `fastapi[all]`) — REST API server with OpenAPI/Swagger auto-docs at `/docs`
- Uvicorn (`uvicorn[standard]`) — ASGI server; dev: `uvicorn src.main:app --reload --port 8000`
- Pydantic v2 (`pydantic>=2.0.0`) — Request/response validation and settings
- Pydantic Settings (`pydantic-settings>=2.0.0`) — Environment config via `mcp/src/core/config.py`

**Core (Frontend):**
- React 19 (`react ^19.2.4`, `react-dom ^19.2.4`) — UI framework
- Vite 8 (`vite ^8.0.4`) — Dev server and bundler; `@vitejs/plugin-react ^6.0.1`
- Sonner 2 (`sonner ^2.0.7`) — Toast notification library

**Testing:**
- pytest (`pytest>=7.0.0`) + pytest-asyncio (`pytest-asyncio>=0.23.0`) — 162 backend unit/integration tests; config at `mcp/pytest.ini` (`asyncio_mode = auto`)
- Playwright (`@playwright/test ^1.59.1`) — E2E tests for dashboard; config at `dashboard/playwright.config.ts`

**Build/Dev:**
- TypeScript compiler (`typescript ~6.0.2`) — `tsc -b && vite build` for production build
- ESLint 9 (`eslint ^9.39.4`, `typescript-eslint ^8.58.0`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`) — Frontend linting
- cross-env (`cross-env ^10.1.0`) — Cross-platform env vars in Playwright webServer config

## Key Dependencies

**Backend Critical:**
- `sqlalchemy>=2.0.0` — ORM with async support; entities at `mcp/src/models/entities.py`
- `aiosqlite>=0.20.0` — Async SQLite driver for SQLAlchemy; connection string: `sqlite+aiosqlite:///./mcp.db`
- `httpx>=0.27.0` — Async HTTP client for GitHub API calls (`mcp/src/services/github_client.py`)
- `google-genai>=1.73.1` — Google Gemini AI SDK; client at `mcp/src/services/llm/client.py`
- `python-jose[cryptography]>=3.3.0` — JWT creation/validation; auth at `mcp/src/core/auth.py`
- `passlib[bcrypt]>=1.7.4` — Password hashing (declared, current auth uses demo role-based login)
- `slowapi>=0.1.9` — Rate limiting on `/findings/{id}/explain` endpoint (`mcp/src/api/analysis.py`)

**Backend Security/Analysis:**
- `sarif-pydantic>=0.6.2` — SARIF 2.1.x parsing for SAST tool outputs
- `cwe2>=3.0.0` — CWE database lookups (`mcp/src/services/enricher.py`)
- `cvss>=3.0.0` — CVSS score handling
- `detect-secrets>=1.5.0` — Secret detection in finding content before LLM submission (`mcp/src/core/guardrails.py`)
- `defusedxml>=0.7.1` — Safe XML parsing for SpotBugs output

**Backend Utilities:**
- `python-dotenv>=1.0.0` — `.env` file loading
- `python-multipart>=0.0.9` — Multipart form support (included via `fastapi[all]`)

**Frontend:**
- No charting library — custom SVG charts built inline in `dashboard/src/components/Charts.tsx` (Sparkline, Donut, Heatmap, AreaTrend)
- Native `fetch` API — typed API client at `dashboard/src/api/client.ts`; no axios or SDK

## Configuration

**Environment (Backend):**
- Config source: `mcp/.env` (via `pydantic-settings`, `SettingsConfigDict(env_file=".env")`)
- Config class: `mcp/src/core/config.py` → `Settings`
- Required variables:
  - `GITHUB_TOKEN` — GitHub PAT (scopes: `repo`, `workflow`)
  - `GITHUB_OWNER` — GitHub username/org
  - `GITHUB_REPO` — Target repository name
  - `GEMINI_API_KEY` — Google AI API key
  - `SECRET_KEY` — JWT signing secret (min 32 chars)
- Optional variables with defaults:
  - `DATABASE_URL` — `sqlite+aiosqlite:///./mcp.db`
  - `GEMINI_MODEL` — `gemini-3.1-pro-preview`
  - `GEMINI_MAX_RETRIES` — `3`
  - `ACCESS_TOKEN_EXPIRE_MINUTES` — `480`
  - `POLLING_INTERVAL_SECONDS` — `300`
  - `POLLING_WORKFLOW_NAME` — `CI Workflow`
  - `POLLING_BRANCH` — `main`
  - `APP_ENV` — `development` / `production` / `testing`
  - `CI_API_KEY` — API key for CI→MCP (empty = auth disabled)
  - `CI_WEBHOOK_TOKEN` — Webhook auth token (empty = disabled)

**Environment (Frontend):**
- `VITE_API_URL` — Backend base URL (default: `http://localhost:8000`); read in `dashboard/src/api/client.ts`

**Build:**
- `dashboard/vite.config.ts` — Minimal Vite config with React plugin
- `dashboard/tsconfig.json`, `dashboard/tsconfig.app.json`, `dashboard/tsconfig.node.json` — TypeScript project references

## Database

**Engine:** SQLite (file: `mcp/mcp.db`; test: `mcp/test.db`; E2E: in-memory `sqlite+aiosqlite:///:memory:`)

**ORM:** SQLAlchemy 2.0 async (`create_async_engine`, `async_sessionmaker`, `AsyncSession`); engine init at `mcp/src/core/db.py`

**Schema:** Three tables — `projects`, `artifacts`, `findings`; defined as SQLAlchemy ORM models in `mcp/src/models/entities.py`

**Migrations:** No Alembic. Schema evolution via idempotent `ALTER TABLE ADD COLUMN` in `_migrate_schema()` function in `mcp/src/core/db.py`, called on every server startup via `init_db()`.

## Infrastructure

**Deployment:** Local / dev-only — no Docker, no Kubernetes, no cloud deployment configuration detected in repo.

**Dev Tunnel:** `ngrok` referenced in `run.txt` for exposing local server: `ngrok.exe http 8000`

**Process Model:** Single Python process; background GitHub polling via `asyncio.create_task` (not a separate worker).

**CORS:** Wildcard `allow_origins=["*"]` in `development` and `testing` env; locked down (empty list) in `production`.

**API Documentation:** Auto-generated Swagger UI at `http://localhost:8000/docs` (FastAPI built-in).

---

*Stack analysis: 2026-04-28*

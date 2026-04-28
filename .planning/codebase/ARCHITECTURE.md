<!-- refreshed: 2026-04-28 -->
# Architecture

**Analysis Date:** 2026-04-28

## System Overview

```text
┌──────────────────────────────────────────────────────────────────┐
│                      Developer Workflow                           │
│                   git push → GitHub Actions                       │
└──────────────────────────┬───────────────────────────────────────┘
                           │ CI triggers SAST tools in parallel
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│              GitHub Actions CI/CD Pipeline                        │
│  Semgrep │ CodeQL │ ESLint │ SpotBugs │ OWASP Dep-Check │ Trivy  │
│                  Uploads artifacts: SARIF / XML / JSON            │
└──────────────────────────┬───────────────────────────────────────┘
          poll (every 5m)  │  OR  webhook POST /webhook/pipeline-complete
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│              MCP Gateway — FastAPI (Python 3.13)                  │
│  `mcp/src/main.py`                                                │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Background Poller  `mcp/src/services/poller.py`            │ │
│  │  GitHubPoller → GitHubClient → list workflow runs           │ │
│  └───────────────────────────┬─────────────────────────────────┘ │
│                              │ new run detected                   │
│                              ▼                                    │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  SecurityProcessor  `mcp/src/services/processor.py`         │ │
│  │  fetch → ScrubbingService → NormalizerFactory → Enricher    │ │
│  └───────────────────────────┬─────────────────────────────────┘ │
│                              │ Finding rows                       │
│                              ▼                                    │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  SQLite DB  (SQLAlchemy 2.0 async + aiosqlite)              │ │
│  │  `mcp/src/core/db.py`                                       │ │
│  │  Tables: projects, artifacts, findings                      │ │
│  └───────────────────────────┬─────────────────────────────────┘ │
│                              │                                    │
│  REST API (3 routers):       │                                    │
│  artifacts_router  `mcp/src/api/artifacts.py`                     │
│  analysis_router   `mcp/src/api/analysis.py`   ← Gemini AI        │
│  chat_router       `mcp/src/api/chat.py`        ← JWT ChatOps     │
└──────────────────────────────┬───────────────────────────────────┘
                               │ REST API + JWT (Bearer)
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│              Web Dashboard — React 19 + TypeScript                │
│  `dashboard/src/`                                                 │
│                                                                   │
│  App.tsx → Shell (Sidebar + Topbar) → Pages                       │
│  Overview │ Vulnerabilities │ Pipelines │ Chat │ Reports          │
│                                                                   │
│  `dashboard/src/api/client.ts`  — typed fetch wrapper + JWT       │
└──────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| FastAPI app | Entry point, router registration, lifespan (DB init + poller start) | `mcp/src/main.py` |
| GitHubPoller | Background asyncio task — polls GitHub every N seconds for new CI runs | `mcp/src/services/poller.py` |
| GitHubClient | GitHub REST API calls: list runs, list/fetch/download artifacts, dispatch workflow, rerun | `mcp/src/services/github_client.py` |
| SecurityProcessor | Pipeline orchestrator: fetch → scrub → normalize → enrich → deduplicate → store | `mcp/src/services/processor.py` |
| ScrubbingService | PII scrubbing (email, IP, secrets via detect-secrets) before any data reaches AI | `mcp/src/core/guardrails.py` |
| InjectionGuardrail | Prompt injection detection and content length limiting | `mcp/src/core/guardrails.py` |
| NormalizerFactory | Selects correct parser by filename; normalizes SARIF/XML/JSON → `FindingCreate` | `mcp/src/services/normalizer.py` |
| DataEnricher | Adds CWE description, CVSS score, OWASP Top 10 2021 mapping to each finding | `mcp/src/services/enricher.py` |
| LLMAnalysisService | Builds prompt, calls GeminiClient, stores structured analysis on Finding | `mcp/src/services/llm/service.py` |
| GeminiClient | `google-genai` SDK wrapper with exponential backoff retry (429/503) | `mcp/src/services/llm/client.py` |
| CommandService | Dispatches 7 ChatOps slash commands (/explain, /fix, /scan, /rerun, /approve, /revoke, /report) | `mcp/src/services/command_service.py` |
| ReportService | Generates downloadable HTML security report | `mcp/src/services/report_service.py` |
| artifacts_router | REST endpoints: /projects, /findings, /github/runs, /artifacts/process, /webhook | `mcp/src/api/artifacts.py` |
| analysis_router | REST endpoint: POST /findings/{id}/explain (rate-limited via slowapi) | `mcp/src/api/analysis.py` |
| chat_router | REST endpoints: /api/chat/{command,message,report,auth/token} | `mcp/src/api/chat.py` |
| ORM entities | Project, Artifact, Finding with audit trail columns | `mcp/src/models/entities.py` |
| Pydantic schemas | FindingCreate, FindingOut, CommandRequest/Response, AnalysisResult, TokenRequest/Response | `mcp/src/models/schemas.py` |
| JWT auth | HS256 token issue + verification, 3-role RBAC (developer/security_lead/admin) | `mcp/src/core/auth.py` |
| Settings | Pydantic-settings config loaded from `.env` | `mcp/src/core/config.py` |
| API client | Typed fetch wrapper with JWT injection, used by all React pages | `dashboard/src/api/client.ts` |
| App.tsx | Root: page routing (state-based, no router lib), polling interval for new findings | `dashboard/src/App.tsx` |
| Shell | Sidebar + Topbar layout component; defines `PageId` type | `dashboard/src/components/Shell.tsx` |
| Pages | Overview, Vulns, Pipelines, Chat, Reports, Settings | `dashboard/src/pages/` |

## Pattern Overview

**Overall:** Two-tier monorepo — FastAPI backend + React SPA frontend. Backend follows layered architecture (API → Service → Repository). No shared runtime; frontend communicates via HTTP REST.

**Key Characteristics:**
- Backend is fully async (FastAPI + asyncio + aiosqlite)
- Single-process deployment: background poller runs as an asyncio task inside uvicorn
- State-based SPA routing (no React Router): `useState<PageId>` in `App.tsx`
- No message broker — all inter-component calls are direct async function calls within the Python process
- Deduplication enforced at ingestion time via SHA-256 hash of (rule_id + file_path + message)

## Layers

**API Layer:**
- Purpose: HTTP request handling, auth enforcement, parameter validation, response serialization
- Location: `mcp/src/api/`
- Contains: Three FastAPI routers — `artifacts.py`, `analysis.py`, `chat.py`
- Depends on: Service layer, ORM models, Pydantic schemas
- Used by: Dashboard frontend, CI pipeline (webhook/API key)

**Service Layer:**
- Purpose: Business logic, orchestration, external API calls
- Location: `mcp/src/services/`
- Contains: `processor.py`, `poller.py`, `normalizer.py`, `enricher.py`, `github_client.py`, `command_service.py`, `report_service.py`, `llm/`
- Depends on: Core layer (config, db, guardrails), models
- Used by: API layer

**LLM Sub-layer:**
- Purpose: Google Gemini integration isolated from rest of services
- Location: `mcp/src/services/llm/`
- Contains: `client.py` (SDK wrapper), `prompts.py` (prompt builder + system instructions), `schemas.py` (structured output schema), `service.py` (analysis orchestration)
- Depends on: `google-genai` SDK, `mcp/src/core/config.py`
- Used by: `LLMAnalysisService`, `CommandService`, `chat_router`

**Core Layer:**
- Purpose: Cross-cutting infrastructure: database, auth, config, security guardrails
- Location: `mcp/src/core/`
- Contains: `db.py`, `auth.py`, `config.py`, `guardrails.py`
- Depends on: SQLAlchemy, python-jose, pydantic-settings, detect-secrets
- Used by: All other layers

**Model Layer:**
- Purpose: ORM entity definitions and Pydantic I/O schemas
- Location: `mcp/src/models/`
- Contains: `entities.py` (SQLAlchemy ORM), `schemas.py` (Pydantic schemas)
- Depends on: Core layer (Base class from `db.py`)
- Used by: API layer and Service layer

**Frontend Layer:**
- Purpose: React SPA — displays findings, runs, chat, reports; communicates only via REST
- Location: `dashboard/src/`
- Depends on: Backend REST API via `dashboard/src/api/client.ts`

## Data Flow

### Primary Path: CI artifact ingestion via polling

1. `GitHubPoller.start()` loops every `POLLING_INTERVAL_SECONDS` (`mcp/src/services/poller.py:39`)
2. `GitHubPoller._poll()` calls `GitHubClient.list_workflow_runs()` → filters runs newer than `last_processed_run_id` (`mcp/src/services/poller.py:55`)
3. `SecurityProcessor.process_run()` fetches all artifacts for the run, filters by `_is_security_artifact()` (`mcp/src/services/processor.py:73`)
4. For each security artifact: creates `Artifact` DB row (status=`pending`), queues `process_artifact()` (`mcp/src/services/processor.py:86-98`)
5. `SecurityProcessor._run()` calls `GitHubClient.fetch_artifact()` → downloads ZIP, extracts files (`mcp/src/services/processor.py:104`)
6. `ScrubbingService.scrub_content()` strips PII/secrets from raw file content (`mcp/src/core/guardrails.py:19`)
7. `NormalizerFactory.get()` selects parser by filename extension/tool (`mcp/src/services/normalizer.py`)
8. `BaseNormalizer.normalize()` → `list[FindingCreate]`; `deduplicate()` removes seen hashes
9. `DataEnricher.enrich()` adds CWE description, CVSS score, OWASP category (`mcp/src/services/enricher.py`)
10. `compute_dedup_hash()` computes SHA-256, `Finding` ORM objects inserted to SQLite (`mcp/src/services/processor.py:162-184`)
11. `Artifact.status` updated to `processed` or `failed` (`mcp/src/services/processor.py:119,127`)

### Alternative Path: webhook ingestion

1. GitHub Actions CI posts to `POST /webhook/pipeline-complete` with `run_id` (`mcp/src/api/artifacts.py:161`)
2. Bearer token validated against `CI_WEBHOOK_TOKEN`
3. Project auto-created if not exists; `SecurityProcessor.process_run()` queued as `BackgroundTask`
4. Same pipeline as steps 4-11 above

### AI Analysis Path

1. Dashboard calls `POST /findings/{id}/explain` (`mcp/src/api/analysis.py:25`)
2. `LLMAnalysisService.analyze_finding()` builds structured prompt via `build_prompt()` (`mcp/src/services/llm/service.py:44`)
3. `GeminiClient.analyze()` calls Gemini with `response_schema=AnalysisOutput` (structured JSON output) — exponential backoff on 429/503 (`mcp/src/services/llm/client.py:22`)
4. `AnalysisOutput` validated via `model_validate_json(response.text)` (`mcp/src/services/llm/client.py:37`)
5. `Finding.status` → `ai_analyzed`; `Finding.ai_analysis` → JSON blob stored in SQLite (`mcp/src/services/llm/service.py:68-69`)
6. `AnalysisResult` returned to frontend (7 fields: explanation_vi, impact_vi, remediation_diff, severity, cwe_reference, confidence, vulnerability_id)

### ChatOps Path

1. Dashboard `POST /api/chat/command` with JWT Bearer token (`mcp/src/api/chat.py:41`)
2. `get_current_user()` validates JWT, extracts role (`mcp/src/core/auth.py:24`)
3. Role checked against `COMMAND_ROLES` map (`mcp/src/api/chat.py:28-36`)
4. `CommandService.handle()` dispatches to per-command handler (`mcp/src/services/command_service.py:31`)
5. `/approve` and `/revoke` validate `justification >= 20 chars`, check current status, update audit trail columns on `Finding` (`mcp/src/services/command_service.py`)
6. `/scan` triggers `GitHubClient.dispatch_workflow()` → `workflow_dispatch` event (`mcp/src/services/github_client.py:57`)

### Free-form Chat Path

1. Dashboard `POST /api/chat/message` with user text
2. `_suggested_command()` regex-matches Vietnamese phrases to slash commands (`mcp/src/api/chat.py:105`)
3. `_build_context()` queries SQLite for specific finding + top 5 critical/high findings (`mcp/src/api/chat.py:133`)
4. `GeminiClient.chat()` called with context prefix; returns plain Vietnamese text (`mcp/src/services/llm/client.py:51`)
5. Response + optional `suggested_command` chip returned to frontend

**State Management (Frontend):**
- No global state manager (Redux, Zustand, etc.)
- `App.tsx` holds: `active: PageId`, `theme`, `openVulnId`, `vulnCount` via `useState`
- Pages fetch data via `api.*` calls on mount and on relevant tab activation; no shared cache
- Auth token stored in `localStorage`, read on startup via `localStorage.getItem('auth_token')`
- Polling: `App.tsx` fetches finding count every 60 seconds for toast notifications

## Key Abstractions

**BaseNormalizer:**
- Purpose: Abstract parser for one SAST tool's output format; subclasses cover SARIF, SpotBugs XML, DepCheck JSON, Trivy JSON
- Examples: `SARIFNormalizer`, `SpotBugsXMLNormalizer`, `DepCheckNormalizer`, `TrivyNormalizer` in `mcp/src/services/normalizer.py`
- Pattern: Strategy pattern — `NormalizerFactory.get(filename, content)` returns correct subclass

**FindingCreate (internal DTO):**
- Purpose: Unified intermediate schema after normalization, before DB write
- File: `mcp/src/models/schemas.py:8`

**Finding (ORM entity):**
- Purpose: Persistent representation of a security finding with full lifecycle: `pending_review` → `ai_analyzed` → `APPROVED` / `REVOKED`
- File: `mcp/src/models/entities.py:43`

**GeminiClient:**
- Purpose: Single integration point for all Gemini calls (structured analysis + free-form chat)
- File: `mcp/src/services/llm/client.py`
- Pattern: Thin SDK wrapper with retry logic; used as singleton per `chat_router` instance

## Entry Points

**Backend server:**
- Location: `mcp/src/main.py`
- Triggers: `uvicorn src.main:app --reload --port 8000`
- Responsibilities: Create FastAPI app, register routers, run `init_db()`, start `GitHubPoller` background task

**Frontend dev server:**
- Location: `dashboard/src/main.tsx`
- Triggers: `npm run dev` (Vite)
- Responsibilities: Mount React root, apply `tokens.css` design system

**Test mode:**
- Location: `mcp/src/main.py:22-24` + test-only endpoints at `mcp/src/main.py:79-119`
- Triggers: `TEST_MODE=1 uvicorn ...`
- Responsibilities: Uses SQLite in-memory, bypasses LLM, exposes `/test/reset` and `/test/inject-finding`

## Architectural Constraints

- **Threading:** Single-process async event loop (uvicorn). Background poller runs as asyncio task inside the same process — not a separate worker. Gemini SDK calls are blocking; wrapped in `asyncio.to_thread()` to avoid blocking the event loop (`mcp/src/services/llm/client.py:28,67`).
- **Global state:** Module-level singleton `settings = Settings()` at `mcp/src/core/config.py:24`. Module-level `_gemini: GeminiClient | None = None` singleton in `mcp/src/api/chat.py:95`. `_command_service = CommandService()` in `mcp/src/api/chat.py:38`.
- **Circular imports:** None detected — layers have clean dependency direction: api → services → core/models.
- **No migration tool:** Schema changes use manual `ALTER TABLE` in `_migrate_schema()` at `mcp/src/core/db.py:24`. Tables created via `Base.metadata.create_all` on every startup.
- **CORS:** Open (`allow_origins=["*"]`) in development/testing mode; empty origins in production (`mcp/src/main.py:48-51`).
- **No API versioning:** All endpoints at root path; no `/v1/` prefix.

## Anti-Patterns

### No API versioning

**What happens:** All REST endpoints are mounted at root (e.g., `/findings`, `/api/chat/command`) with no version prefix.
**Why it's wrong:** Breaking changes to any endpoint will break all Dashboard clients with no migration path.
**Do this instead:** Add `/v1/` prefix to all routers in `mcp/src/main.py` via `APIRouter(prefix="/v1")`.

### Singleton service objects in module scope

**What happens:** `_command_service = CommandService()` and `_gemini: GeminiClient | None` are created at module import time in `mcp/src/api/chat.py`.
**Why it's wrong:** Makes dependency injection and testing harder; these objects hold no state so the pattern provides no benefit.
**Do this instead:** Use FastAPI `Depends()` with a factory function (pattern already used correctly for `LLMAnalysisService` in `mcp/src/api/analysis.py:21`).

### Frontend state polling instead of push

**What happens:** `App.tsx` polls `/findings` every 60 seconds via `setInterval` for new finding count notifications.
**Why it's wrong:** Generates constant HTTP traffic; notifications are delayed up to 60s.
**Do this instead:** Use WebSocket or Server-Sent Events for real-time push from backend when new findings are ingested.

## Error Handling

**Strategy:** Exceptions are caught at the service layer; API layer translates to HTTP error codes. Per-file normalization errors are isolated — one bad file does not fail the entire batch.

**Patterns:**
- `processor.py` wraps `_run()` in try/except: sets `artifact.status = "failed"` and re-raises so caller can log (`mcp/src/services/processor.py:125-129`)
- Per-file normalization: `try/except Exception` with `continue` — bad files logged and skipped (`mcp/src/services/processor.py:150-153`)
- `GeminiClient` raises `RuntimeError` after exhausting retries; `analysis_router` catches it and returns HTTP 503 (`mcp/src/api/analysis.py:46-47`)
- `chat_router.chat_message()` catches all Gemini exceptions and falls back to a static help message (`mcp/src/api/chat.py:178-186`)
- FastAPI `HTTPException` used throughout API layer for 400/403/404/422 responses

## Cross-Cutting Concerns

**Logging:** Python `logging` module via `log = logging.getLogger(__name__)` in every module. No structured logging or centralized aggregation configured.

**Validation:** Pydantic models at all API boundaries (`FindingCreate`, `FindingOut`, `CommandRequest`, `AnalysisResult`). SQLAlchemy ORM for DB writes.

**Authentication:** JWT HS256 via `python-jose`. Demo-mode `POST /api/chat/auth/token` issues tokens without password. Protected endpoints use `Depends(get_current_user)`. CI pipeline uses `X-API-Key` header or `Authorization: Bearer <CI_WEBHOOK_TOKEN>` depending on endpoint.

**Security guardrails:** Applied at ingestion time (`ScrubbingService.scrub_content()`) and at AI call time (`InjectionGuardrail.check()`). PII (email, IP) replaced with placeholders. Secrets detected via `detect-secrets` library. Zip Slip + Zip Bomb protection in `GitHubClient.fetch_artifact()`.

---

*Architecture analysis: 2026-04-28*

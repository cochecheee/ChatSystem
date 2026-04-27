# Project State: Security-Integrated CI/CD System

## Status
- **Phase:** Phase 1 (Core System Initialization) → chuẩn bị Phase 2.
- **Progress:** Phase 1 hoàn thành scaffold. Đang discuss và finalize planning trước khi implement.

Last activity: 2026-04-28 - Completed quick task 260428-29v: Fix pipeline tab refetch on tab activation + CI/CD split sidebar

## Data Strategy
- **Development & Production:** Dùng data thật — GitHub CI artifacts thật + Gemini API thật.
  - Cần cấu hình `.env` với `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO`, `GEMINI_API_KEY` thật trước khi chạy.
  - KHÔNG có mock mode cho server (không có `DEV_MOCK=true` hay tương tự).
- **Tests (pytest + Playwright):** Dùng mock/fixture để deterministic, nhanh, không tốn quota.
  - pytest: mock `GeminiClient` và `GitHubClient` bằng `unittest.mock`.
  - Playwright E2E: `TEST_MODE=1` bypass Gemini, mock GitHub API qua `page.route()`, SQLite `:memory:`.

## Current Task
- Phase 3, Plan 03-01: Gemini Client Integration & Mocking Infrastructure.
- Phase 2 integration fixes đang hoàn thiện (xem Completed bên dưới).

## Key Decisions

### Architecture
- **Structure:** Thư mục độc lập cho `mcp/` và `dashboard/`.
- **Framework Backend:** Python FastAPI + SQLAlchemy async + aiosqlite (SQLite).
- **Framework Frontend:** Vite + React 19 + TypeScript.
- **ChatOps:** Tích hợp trực tiếp vào Web Dashboard (không dùng Slack/Teams).

### Security & Auth
- **Auth model:** 2 tầng:
  - Tầng 1: API Key (`X-API-Key` header) cho CI/CD pipeline → MCP calls.
  - Tầng 2: JWT + Role-based cho Dashboard → MCP calls.
- **Roles:** `admin`, `security_lead`, `developer`.
  - `developer`: xem findings, dùng `/explain`, `/fix`.
  - `security_lead`: thêm `/rerun`, `/approve`.
  - `admin`: thêm quản lý users.
- **Auth implementation:** `python-jose` (JWT) + `passlib[bcrypt]` (password hashing).

### AI / LLM
- **SDK:** `google-genai>=1.73.1` — SDK mới chính thức (KHÔNG dùng `google-generativeai` đã deprecated).
- **Model:** Configurable qua env var `GEMINI_MODEL`, default `gemini-2.5-flash`.
- **Rate limiting:** `asyncio.Semaphore(3)` concurrent calls + `slowapi` middleware.
- **Output schema:** 7 fields — `vulnerability_id`, `explanation_vi`, `impact_vi`, `remediation_diff`, `severity`, `cwe_reference`, `confidence`.
- **Prompt language:** Tiếng Việt.
- **Remediation:** Unified Diff format, human-in-the-loop bắt buộc (không auto-apply).

### SAST & CI/CD
- **Architecture:** Java target repo riêng — pipeline chạy trên Java repo, kết quả gửi về MCP Gateway của chat-system.
- **Target project:** Java 21 + Gradle — có Thymeleaf frontend (JS/TS).
- **SpotBugs:** `com.github.spotbugs` Gradle plugin v6, built-in SARIF output (không cần converter).
- **ESLint:** Scan Thymeleaf static JS/TS trong `src/main/resources/static/`.
- **Artifact fetch:** MCP Gateway **polling** GitHub API mỗi 5 phút (không dùng webhook).
- **Poller:** `mcp/src/services/poller.py` — background AsyncIO task, lưu `last_processed_run_id` trong DB.
- **SARIF version fix:** `sarif-pydantic` latest là `0.6.2` (không phải `^2.1.0` như research gốc).

### Testing
- **Style:** Code trước, viết test sau (không TDD).
- **Backend:** `pytest` + `pytest-asyncio`.
- **Frontend:** Vitest + React Testing Library.
- **E2E:** Playwright.

## Completed
- Phase 1: ✅ Scaffold, requirements, dev env setup
- Phase 2, 02-01: ✅ FastAPI + SQLAlchemy DB layer (Project, Artifact, Finding models)
- Phase 2, 02-02: ✅ GitHubClient (artifact fetch + Zip Slip/Bomb protection), ScrubbingService (PII + secrets), InjectionGuardrail
- Phase 2, 02-03: ✅ SarifNormalizer, SpotBugsXMLNormalizer, ESLintNormalizer, DepCheckNormalizer, TrivyJsonNormalizer, NormalizerFactory (smart JSON detection), DataEnricher (CWE/OWASP 2021/CVSS)
- Phase 2, 02-04: ✅ SecurityProcessor (end-to-end pipeline), GitHubPoller (background task, last_processed_run_id), REST API (POST /artifacts/process, GET /findings, POST /projects), E2E tests
- Phase 2, integration fixes: ✅ Smart JSON routing (DepCheck/Trivy/SARIF-in-JSON/metadata skip), artifact name filtering (_SECURITY_ARTIFACT_NAMES), POST /webhook/run-complete endpoint
- Phase 4: ✅ CI pipeline đã build và running trên repo SAST_CICD (6 tools: Semgrep, CodeQL, SpotBugs, ESLint-SARIF, Trivy, OWASP Dep-Check). Pipeline có 3 security gates + SonarCloud + webhook notify đến MCP Gateway.

## Blockers
- Không còn blockers — GitHub PAT và Gemini API Key đã cấu hình trong .env.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260428-29v | Fix pipeline tab: refetch on tab activation + CI/CD split sidebar | 2026-04-28 | 8abee9e | [260428-29v-fix-pipeline-tab-1-refetch-on-tab-activa](.//quick/260428-29v-fix-pipeline-tab-1-refetch-on-tab-activa/) |

### ChatOps Commands (Final Assignment)
- **Phase 5** (simple read-only, frontend calls API trực tiếp): `/status`, `/results`
- **Phase 6** (complex backend actions): `/explain`, `/fix`, `/scan`, `/rerun`, `/approve`, `/revoke`, `/report`
- `/approve` và `/revoke`: min 20 chars justification, lưu audit trail (who/when)
- `/report`: HTML file download, server-side render bằng Python f-string
- Business rules: không approve APPROVED finding, không revoke REVOKED finding, không approve INFO severity
- E2E: Playwright full-stack Chromium only, TEST_MODE=1 bypass LLM, GitHub mock qua page.route()

## Next Steps
1. Implement Phase 2: MCP Gateway Server (02-01 → 02-02 → 02-03 → 02-04).
2. Implement Phase 3: LLM Orchestrator (03-01 → 03-02 → 03-03).
3. Implement Phase 4: CI/CD Pipeline trên Java repo.
4. Implement Phase 5: Web Dashboard.
5. Implement Phase 6: Advanced Features + E2E.

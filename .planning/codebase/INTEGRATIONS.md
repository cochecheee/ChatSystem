# External Integrations

**Analysis Date:** 2026-04-28

## APIs & External Services

**GitHub Actions / GitHub REST API:**
- Purpose: Poll CI/CD workflow runs, list and download SARIF/XML/JSON artifacts, dispatch workflows, re-run failed jobs
- SDK/Client: Raw `httpx` async HTTP client; no official GitHub SDK
- Implementation: `mcp/src/services/github_client.py` → `GitHubClient`
- API base: `https://api.github.com`
- API version header: `X-GitHub-Api-Version: 2022-11-28`
- Auth: `Authorization: Bearer <GITHUB_TOKEN>`
- Operations used:
  - `GET /repos/{owner}/{repo}/actions/runs` — list workflow runs
  - `GET /repos/{owner}/{repo}/actions/runs/{run_id}/artifacts` — list artifacts per run
  - `GET /repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip` — download artifact ZIP
  - `POST /repos/{owner}/{repo}/actions/workflows/{filename}/dispatches` — manual trigger
  - `POST /repos/{owner}/{repo}/actions/runs/{run_id}/rerun` — re-run workflow
- Env vars: `GITHUB_TOKEN`, `GITHUB_OWNER`, `GITHUB_REPO`

**Google Gemini AI:**
- Purpose: AI-powered security finding analysis with Vietnamese-language output; structured JSON responses with 7 fields (explanation, impact, remediation_diff, severity, CWE reference, confidence); free-form ChatOps assistant
- SDK/Client: `google-genai>=1.73.1` (`from google import genai`)
- Implementation: `mcp/src/services/llm/client.py` → `GeminiClient`
- Default model: `gemini-3.1-pro-preview` (configurable via `GEMINI_MODEL`)
- Response schema: `mcp/src/services/llm/schemas.py` → `AnalysisOutput` (Pydantic model enforced via `response_mime_type="application/json"`)
- Error handling: Exponential backoff (2^attempt seconds) on HTTP 429, 503, and `RESOURCE_EXHAUSTED`; max retries: `GEMINI_MAX_RETRIES` (default 3)
- Two usage modes:
  - `GeminiClient.analyze()` — structured JSON for finding analysis (called by `/findings/{id}/explain`)
  - `GeminiClient.chat()` — free-form Vietnamese text for ChatOps assistant (called by `/api/chat/message`)
- Prompts: `mcp/src/services/llm/prompts.py` (`SYSTEM_INSTRUCTION`, `CHAT_SYSTEM_INSTRUCTION`)
- Env vars: `GEMINI_API_KEY`, `GEMINI_MODEL`

**ngrok (dev tunnel):**
- Purpose: Expose local backend server (`localhost:8000`) to the internet for webhook/testing scenarios
- Referenced in: `run.txt`
- Tool: `ngrok.exe http 8000`
- Not automated; manual developer step

## SAST Tools (CI/CD Consumers — not called directly by backend)

The MCP backend **consumes** artifacts produced by these tools running inside GitHub Actions. It does not invoke them directly.

| Tool | Output Format | Artifact Name Pattern |
|------|--------------|----------------------|
| Semgrep | SARIF | `semgrep-report` |
| CodeQL | SARIF | `codeql-report` |
| ESLint (with SARIF reporter) | SARIF | fixed name |
| SpotBugs | XML | fixed name |
| OWASP Dependency-Check | JSON | fixed name |
| Trivy (filesystem + container image scan) | JSON/SARIF | `trivy-image-scan-<run_number>` (prefix matching) |

Parser: `mcp/src/services/normalizer.py` — lenient walker (not strict pydantic), each file isolated so one bad file doesn't kill entire batch.

## Authentication Providers

**JWT (self-issued):**
- No third-party OAuth or SSO
- Backend issues JWT tokens itself via `create_access_token()` in `mcp/src/core/auth.py`
- Algorithm: HS256
- Signing key: `SECRET_KEY` env var (min 32 chars)
- TTL: `ACCESS_TOKEN_EXPIRE_MINUTES` (default 480 minutes = 8 hours)
- Library: `python-jose[cryptography]>=3.3.0`
- Token endpoint: `POST /api/chat/auth/token` — accepts `{username, role}` (demo login, no password verification in current implementation)
- RBAC roles: `developer`, `security_lead`, `admin`
- Role enforcement: `mcp/src/api/chat.py` (`COMMAND_ROLES` dict) + `get_current_user` dependency

**API Key (CI pipeline authentication):**
- Header: `X-API-Key`
- Variable: `CI_API_KEY` — if empty, auth is disabled (dev/test mode)
- Used on: `POST /artifacts/process`
- Implementation: `mcp/src/api/artifacts.py` → `require_api_key`

**Webhook Token:**
- Header-based token auth for `POST /webhook/pipeline-complete`
- Variable: `CI_WEBHOOK_TOKEN` — if empty, auth disabled
- Implementation: `mcp/src/api/artifacts.py`

## Messaging & Queues

**None — no message queue used.**

Background polling implemented as a plain `asyncio.create_task` infinite loop inside the same FastAPI process:
- `mcp/src/services/poller.py` → `GitHubPoller.start()` — polls GitHub REST API every `POLLING_INTERVAL_SECONDS` (default 300s = 5 minutes)
- Started in FastAPI lifespan: `mcp/src/main.py`

Webhook alternative: `POST /webhook/pipeline-complete` can receive push notifications from GitHub Actions instead of relying on polling.

## Monitoring & Observability

**Logging:**
- Standard Python `logging` module throughout all service/API files
- No structured logging library (no loguru, structlog)
- Log level: default Python logging config (no explicit level set in code; uvicorn provides access logs)
- Key log sites:
  - `mcp/src/services/poller.py` — polling cycle events, new runs found, errors
  - `mcp/src/services/llm/client.py` — Gemini retry warnings and errors
  - `mcp/src/main.py` — background poller start

**Error Tracking:**
- None — no Sentry, Datadog, or similar APM/error tracking

**Metrics:**
- None — no Prometheus, StatsD, or metrics endpoint

**Health Check:**
- `GET /health` → `{"status": "healthy"}` — simple liveness endpoint (`mcp/src/main.py`)

**API Documentation:**
- FastAPI auto-generated Swagger UI at `http://localhost:8000/docs`

## CI/CD

**Pipeline Platform: GitHub Actions**
- The repository's own CI pipeline (in the target repo being monitored, not this repo) runs SAST tools: Semgrep, CodeQL, ESLint, SpotBugs, OWASP Dependency-Check, Trivy
- No `.github/workflows/` directory detected in this `chat-system` repo itself — the project does not have CI for its own code
- The MCP backend monitors a *separate* configured repo (`GITHUB_OWNER`/`GITHUB_REPO`)

**Artifact Registry:**
- GitHub Actions artifact storage (via GitHub API) — no external registry

**Deployment:**
- No deployment pipeline, no Dockerfile, no docker-compose, no Kubernetes manifests detected
- Dev: run manually with `uvicorn` + `npm run dev`

## Security Libraries (On-Premise)

**detect-secrets (Yelp):**
- Purpose: Scan SAST finding content for embedded secrets before sending to Gemini
- Library: `detect-secrets>=1.5.0`
- Implementation: `mcp/src/core/guardrails.py` → `ScrubbingService._scrub_secrets()`
- Mechanism: writes content to a temp file, scans with `SecretsCollection`, replaces detected-secret lines with `[SECRET_SCRUBBED]`

**CWE Database (cwe2):**
- Purpose: Enrich findings with CWE weakness names and OWASP Top 10 2021 category
- Library: `cwe2>=3.0.0`
- Implementation: `mcp/src/services/enricher.py` → `DataEnricher`

**CVSS scoring:**
- Library: `cvss>=3.0.0`
- Implementation: `mcp/src/services/enricher.py` — maps severity string to CVSS score if not already present

**defusedxml:**
- Purpose: Safe XML parsing to prevent XXE attacks when processing SpotBugs XML output
- Library: `defusedxml>=0.7.1`
- Used in: `mcp/src/services/normalizer.py`

## File Security

**Zip Slip + Zip Bomb protection** when downloading GitHub artifact ZIPs:
- Max ZIP size: 50 MB (`_MAX_ZIP_BYTES`)
- Max per-file size: 10 MB (`_MAX_FILE_BYTES`)
- Path traversal check: rejects entries with `..` or absolute paths
- Extension whitelist: only `.sarif`, `.xml`, `.json`
- Implementation: `mcp/src/services/github_client.py` → `GitHubClient._extract_security_files()`

## Rate Limiting

**slowapi:**
- Library: `slowapi>=0.1.9`
- Applied on: `POST /findings/{id}/explain` (Gemini call endpoint)
- Key function: `get_remote_address` (per client IP)
- Implementation: `mcp/src/api/analysis.py`

## Frontend External Dependencies

**No external service calls from frontend.**

- All API calls go to the local MCP Gateway backend (`VITE_API_URL`, default `http://localhost:8000`)
- No CDN-hosted assets, no analytics scripts, no third-party trackers
- Auth token stored in `localStorage` (key: `auth_token`)
- Token management: `dashboard/src/api/client.ts` → `setAuthToken()` / `getAuthToken()`

---

*Integration audit: 2026-04-28*

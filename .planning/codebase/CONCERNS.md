# Technical Concerns

**Analysis Date:** 2026-04-28

---

## Security Concerns

### 1. No-Password Demo Auth Endpoint Left Unrestricted

**File:** `mcp/src/api/chat.py` lines 191-202

`POST /api/chat/auth/token` issues a signed JWT for any (username, role) pair with **zero password verification**. Anyone who can reach the API can self-issue a token with `role=admin`. The code comment explicitly labels it "demo — thesis only", but there is no runtime guard (e.g. `APP_ENV` check) preventing it from being called in production.

**Risk:** Full privilege escalation — anyone can become an admin-role user.

**Fix:** Gate the endpoint behind `APP_ENV == "development"` check, or require a shared secret in the request body. Remove or replace with real identity provider (LDAP, OAuth2) before any production exposure.

---

### 2. Default Weak SECRET_KEY Shipped in Source

**File:** `mcp/src/core/config.py` line 6

```python
SECRET_KEY: str = "change-me-in-production-min-32-chars"
```

If `SECRET_KEY` is never overridden via `.env`, the JWT signing key is a known public string. All JWTs signed with this default key can be forged offline.

**Risk:** Any token produced in a misconfigured deployment is trivially forgeable.

**Fix:** Remove the default value (use `...` to make it a required field), or add a startup assertion that aborts if the key equals the placeholder.

---

### 3. Rate Limiter Instantiated But Never Wired

**File:** `mcp/src/api/analysis.py` lines 8-18

`Limiter` and `slowapi` are imported and a `limiter` object is created, but:
- No `@limiter.limit(...)` decorator is applied to any route.
- `SlowAPIMiddleware` is not registered in `mcp/src/main.py`.
- `app.state.limiter` is never set.

The rate-limiting dependency is installed (`requirements.txt` lists `slowapi>=0.1.9`) but the feature is entirely dead. The `/findings/{finding_id}/explain` endpoint calls Gemini AI on every request — an attacker or misconfigured client could exhaust the API quota.

**Risk:** Gemini API quota exhaustion; denial-of-service via AI endpoint.

**Fix:** Add `@limiter.limit("10/minute")` to `explain_finding` and the `/api/chat/message` endpoint; register `SlowAPIMiddleware` in `main.py`; set `app.state.limiter = limiter`.

---

### 4. InjectionGuardrail Never Called on Chat Input

**File:** `mcp/src/core/guardrails.py` — `InjectionGuardrail` class exists.
**File:** `mcp/src/api/chat.py` lines 163-188 — `chat_message` endpoint.

`InjectionGuardrail` is only used in unit tests (`mcp/tests/test_guardrails_injection.py`). It is **never imported or called** in any production code path. User text submitted via `POST /api/chat/message` goes directly to Gemini without injection scanning.

`ScrubbingService` is used only in `processor.py` for SAST artifacts, not for live chat input.

**Risk:** Direct prompt injection via the chat endpoint — users can attempt to hijack Gemini's system instruction.

**Fix:** Call `InjectionGuardrail().check(request.text)` at the top of `chat_message`, and return HTTP 400 if unsafe. Call `InjectionGuardrail().sanitize()` before passing to `_get_gemini().chat()`.

---

### 5. Several Core Endpoints Lack JWT Authentication

The following routes in `mcp/src/api/artifacts.py` accept unauthenticated requests:

| Endpoint | Method | Risk |
|----------|--------|------|
| `GET /projects` | Open | Lists all projects |
| `POST /projects` | Open | Creates projects without auth |
| `GET /github/runs` | Open | Exposes GitHub run metadata |
| `GET /github/runs/{run_id}/artifacts` | Open | Exposes artifact lists |
| `GET /findings` | Open | Reads all security findings |
| `GET /findings/{finding_id}` | Open | Reads individual finding |
| `GET /github/runs/{run_id}/findings` | Open | Reads all findings per run |
| `POST /github/runs/{run_id}/reprocess` | Open | Destructively deletes and reprocesses findings |

Only `POST /artifacts/process` uses `require_api_key`, and only when `CI_API_KEY` is non-empty. The `GET /findings` family and `POST /reprocess` are entirely unprotected.

**Risk:** Security findings (vulnerabilities in production code) are readable by anyone who can reach the server. The reprocess endpoint allows data destruction without any credential.

**Fix:** Add `Depends(get_current_user)` to findings endpoints. Add `Depends(require_api_key)` or `Depends(get_current_user)` to `reprocess_run`. Enforce `CI_API_KEY` as a required field in production.

---

### 6. CORS Wildcard in Development Mode (May Carry to Production)

**File:** `mcp/src/main.py` lines 48-53

```python
allow_origins=["*"] if settings.APP_ENV in ("development", "testing") else [],
```

When `APP_ENV` is not explicitly set (defaults to `"development"` per `config.py` line 17), CORS is completely open. The `allow_credentials=True` combined with `allow_origins=["*"]` is also an invalid CORS configuration that modern browsers reject — `credentials: include` requires an explicit origin, not a wildcard.

**Risk:** Misconfiguration silently toggles between fully open and fully closed CORS. Production deployments where `APP_ENV` is forgotten remain wide open.

**Fix:** Replace `["*"]` with a configurable `ALLOWED_ORIGINS` env var. Add `allow_credentials=False` when using wildcard or set explicit origins.

---

### 7. Webhook Token Hardcoded in `.env.example`

**File:** `mcp/.env.example` line 45

```
CI_WEBHOOK_TOKEN=VQfwyOv2GPiSVfY4Rgh2KaMUjKLf7o7qkxj7uegEyA4
```

An actual token value is committed to the example file. If anyone reuses this value (copy-paste from docs), they use a publicly known token.

**Risk:** Any attacker who reads this file can trigger webhook payload injection.

**Fix:** Replace with `CI_WEBHOOK_TOKEN=<generate with: python -c "import secrets; print(secrets.token_urlsafe(32))">` placeholder text only.

---

## Technical Debt

### 1. Manual Schema Migration Instead of Alembic

**File:** `mcp/src/core/db.py` lines 24-46

`_migrate_schema` is a hand-rolled migration function using raw `ALTER TABLE` statements. It runs on every server startup, parsing table structure via SQLAlchemy `inspect`. This approach:
- Has no migration history or rollback capability.
- Will silently fail on databases that already have the column with a different type.
- Cannot handle column renames, type changes, or table drops.

**Risk:** Schema drift in long-running deployments; impossible to audit what the database schema was at any point in time.

**Fix:** Introduce Alembic. Run `alembic init` and migrate the startup-migration logic to versioned migration scripts.

---

### 2. Default Gemini Model Is Incorrect

**File:** `mcp/src/core/config.py` line 9

```python
GEMINI_MODEL: str = "gemini-3.1-pro-preview"
```

`gemini-3.1-pro-preview` does not exist as a valid Gemini model name at the time of this analysis. The `.env.example` file correctly overrides to `gemini-2.5-flash`, but any deployment that fails to set `GEMINI_MODEL` in `.env` will use the invalid default, causing runtime errors on every AI call.

**Fix:** Change the default to `"gemini-2.5-flash"` or another confirmed valid model name.

---

### 3. `dedup_hash` Column Has No Unique Constraint

**File:** `mcp/src/models/entities.py` line 58

```python
dedup_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
```

`dedup_hash` is indexed for lookup speed but has no `unique=True`. The deduplication logic in `processor.py` and `normalizer.py` is entirely in-memory and only prevents duplicates within a single batch. Concurrent processing of two runs with overlapping findings will insert duplicate rows.

**Fix:** Add `unique=True` to the column definition and handle the `IntegrityError` in the processor as an expected conflict (skip silently).

---

### 4. `passlib[bcrypt]` Dependency Installed But Never Used

**File:** `mcp/requirements.txt` line 30

`passlib[bcrypt]>=1.7.4` is listed as a dependency. No import of `passlib` exists anywhere in `mcp/src/`. The library was likely added in anticipation of a real password hashing implementation that was never built (superseded by the demo JWT approach).

**Fix:** Remove from `requirements.txt` to reduce attack surface and dependency size.

---

### 5. `sarif-pydantic` Dependency Installed But Abandoned

**File:** `mcp/requirements.txt` line 18; `mcp/src/services/normalizer.py`

`sarif-pydantic>=0.6.2` is installed but the `SarifNormalizer` was rewritten to use a raw JSON dict walk (see the inline comment at line 103) because `sarif-pydantic` was too strict. The package is imported nowhere in production code.

**Fix:** Remove `sarif-pydantic` from `requirements.txt`.

---

## Performance Risks

### 1. Unbounded `SELECT * FROM findings` in Report Generation

**File:** `mcp/src/services/report_service.py` line 37

```python
result = await db.execute(select(Finding))
```

This query loads every finding in the database into memory to render an HTML report. With no `LIMIT`, a large database (thousands of findings across many runs) will OOM the server process.

**Risk:** Memory exhaustion on report generation request; response latency grows unbounded.

**Fix:** Add streaming HTML generation or paginate findings (e.g., top 500 by severity). Add a server-side warning if total findings exceed a threshold.

---

### 2. Background Poller Has No Jitter or Backoff on Success

**File:** `mcp/src/services/poller.py` lines 39-51

The poller wakes every `POLLING_INTERVAL_SECONDS` (default 300s) with a fixed `await asyncio.sleep(self.interval)`. There is no jitter to prevent thundering-herd if multiple instances run, and the interval does not back off when GitHub returns no new runs repeatedly.

**Risk:** Unnecessary GitHub API calls consuming rate-limit quota when there is no CI activity.

**Fix:** Add random jitter (`interval ± 15%`). Consider exponential backoff when no new runs are found for multiple consecutive polls.

---

### 3. `detect-secrets` Uses Temporary File I/O on Every Scrub

**File:** `mcp/src/core/guardrails.py` lines 27-60

`ScrubbingService._scrub_secrets` writes content to a temp file on disk, runs `detect-secrets` scan on it, then reads back results. This file I/O happens for every SAST artifact file during processing. For large artifacts or high-throughput environments this is a bottleneck.

**Risk:** Processing throughput bottleneck; temp file leaks if the process is killed between `NamedTemporaryFile` and `os.unlink`.

**Fix:** Use `detect-secrets` in-memory API if available. Wrap the `finally: os.unlink` with additional `try/except` to ensure cleanup.

---

### 4. `_get_gemini()` Is a Module-Level Singleton with No Thread Safety

**File:** `mcp/src/api/chat.py` lines 95-102

```python
_gemini: GeminiClient | None = None

def _get_gemini() -> GeminiClient:
    global _gemini
    if _gemini is None:
        _gemini = GeminiClient()
    return _gemini
```

This is a lazy singleton on a module-level mutable global. In a multi-worker uvicorn deployment, each worker process has its own copy — the pattern is safe for processes but is a code smell. In asyncio, simultaneous requests could theoretically race on the `None` check before the first assignment completes (though Python's GIL makes this safe for the assignment itself).

**Fix:** Instantiate `GeminiClient` once at app startup (e.g., in `lifespan`) and inject via FastAPI `app.state` rather than using a mutable global.

---

## Missing Patterns

### 1. No Input Length Validation on Chat and Command Endpoints

**Files:** `mcp/src/models/schemas.py`, `mcp/src/api/chat.py`

`ChatMessageRequest.text` and `CommandRequest.justification` are plain `str` with no `max_length` constraint. A client can send megabyte-sized strings to `POST /api/chat/message` or `POST /api/chat/command`. These strings will be forwarded to Gemini, potentially consuming tokens wastefully or triggering errors.

**Fix:** Add Pydantic field constraints:
```python
text: str = Field(..., max_length=4000)
justification: str | None = Field(None, max_length=2000)
```

---

### 2. No Global Error Handler / Exception Middleware

**File:** `mcp/src/main.py`

There is no `@app.exception_handler(Exception)` to catch unhandled exceptions and return a consistent JSON error response. FastAPI's default unhandled exception response leaks stack traces in some configurations.

**Fix:** Add a global exception handler that logs the traceback and returns `{"detail": "Internal server error"}` with HTTP 500.

---

### 3. No Structured Logging — Plain `logging.getLogger` Only

All services use Python's standard `logging.getLogger(__name__)` with no formatting configuration. Log output format, level, and destination are entirely dictated by uvicorn's defaults. There is no request-ID tracing across log lines.

**Risk:** Difficult to correlate logs for a specific request across modules in production.

**Fix:** Configure `logging.basicConfig` or `dictConfig` at startup in `main.py`. Add a middleware that injects a `request_id` into the log context for correlation.

---

### 4. No Retry Logic for Database Operations

**Files:** `mcp/src/services/processor.py`, `mcp/src/services/poller.py`

Database writes in `_run()` and `_poll()` have no retry on transient SQLite lock errors (`OperationalError: database is locked`). SQLite with `aiosqlite` serializes writes — if two background tasks (poller + webhook) attempt to commit simultaneously, one will fail with a lock error and the artifact will be marked `"failed"`.

**Fix:** Wrap `session.commit()` in a retry loop with exponential backoff for `OperationalError`, or consider migrating to PostgreSQL for concurrent workloads.

---

### 5. No Health Check for Dependent Services

**File:** `mcp/src/main.py` lines 65-67

```python
@app.get("/health")
async def health():
    return {"status": "healthy"}
```

The health endpoint always returns 200/healthy regardless of whether the database is reachable, Gemini API key is valid, or GitHub token is configured. A load balancer or orchestrator relying on this endpoint for readiness cannot detect a broken dependency.

**Fix:** Add database connectivity check (`await session.execute(text("SELECT 1"))`), and optionally check that required env vars (GITHUB_TOKEN, GEMINI_API_KEY) are non-empty.

---

## Dependency Health

| Package | Concern |
|---------|---------|
| `python-jose[cryptography]>=3.3.0` | `python-jose` has known CVEs (GHSA-m82w-4xs8-57fx — algorithm confusion). Consider migrating to `PyJWT` with explicit algorithm pinning. |
| `sarif-pydantic>=0.6.2` | Unused in production code — dead dependency, adds attack surface. Remove. |
| `passlib[bcrypt]>=1.7.4` | Unused in production code. Remove. |
| `google-genai>=1.73.1` | Unpinned upper bound. Breaking API changes in future minor versions could silently break AI features. Pin to a known-good version. |
| All deps in `requirements.txt` | No version pinning (upper bounds) on most packages. Consider generating a `requirements-lock.txt` via `pip-compile`. |

---

## Operational Concerns

### 1. SQLite Is Not Suitable for Production Concurrent Load

**File:** `mcp/src/core/config.py` line 5 (default), `mcp/.env.example` line 12

The system defaults to SQLite and the `.env.example` prescribes SQLite for production. SQLite has write serialization and WAL limitations. The combination of an HTTP server + background poller + webhook handler all writing concurrently will produce lock contention.

**Risk:** Data loss or corruption under moderate concurrent write load.

**Recommendation:** Document SQLite as development-only. Provide a PostgreSQL alternative in `DATABASE_URL` docs. Consider adding a startup warning when SQLite is detected and `APP_ENV != "development"`.

---

### 2. Reload Mode Enabled in `__main__` Block

**File:** `mcp/src/main.py` line 124

```python
uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
```

`reload=True` is appropriate for development but the `__main__` block is the documented way to run the server. If someone runs `python -m src.main` in production, auto-reload is enabled, which watches the filesystem and respawns on any file change.

**Fix:** Either remove the `__main__` block and use a `Makefile`/Docker command with explicit `--no-reload`, or add `reload=settings.APP_ENV == "development"`.

---

### 3. No Artifact Retention Management

**File:** `mcp/src/services/processor.py`, `mcp/src/models/entities.py`

Findings, artifacts, and `raw_data` JSON accumulate indefinitely. There is no TTL, archival, or deletion policy. `raw_data` is an unstructured JSON blob stored per-finding — for large SAST reports this can grow significantly.

**Risk:** Unbounded database growth; report generation (`select(Finding)` with no limit) becomes increasingly slow over time.

**Fix:** Add a periodic cleanup task that archives or deletes findings older than a configurable retention period. Add a `LIMIT` to the report query.

---

### 4. `APP_ENV` Default Is `"development"` — Permissive by Default

**File:** `mcp/src/core/config.py` line 17

Forgetting to set `APP_ENV=production` enables: open CORS (`*`), SQLite echo logging, and the auth-disabled fallback paths. The system is permissive by default rather than secure by default.

**Fix:** Consider reversing the default — make `APP_ENV="production"` the default and require explicit `APP_ENV=development` to enable development affordances.

---

## Positive Highlights

These areas demonstrate strong engineering practice:

1. **Guardrails Architecture** — `mcp/src/core/guardrails.py` shows deliberate design: `ScrubbingService` removes secrets/PII/IPs from SAST data before it reaches the LLM, and `InjectionGuardrail` has a clean `check()` / `sanitize()` API. The pattern is solid; it only needs to be wired into the chat endpoint as well.

2. **Zip Slip and Zip Bomb Protection** — `mcp/src/services/github_client.py` lines 108-128 explicitly guard against directory traversal (`..` in paths, absolute paths), enforces per-file and total ZIP size limits, and restricts to allow-listed extensions. This is security-conscious artifact handling.

3. **Defusedxml for XML Parsing** — `mcp/src/services/normalizer.py` uses `defusedxml` instead of stdlib `xml.etree.ElementTree`, preventing Billion Laughs and XXE attacks on SpotBugs XML reports.

4. **Role-Based Command Dispatch** — `mcp/src/api/chat.py` `COMMAND_ROLES` dict provides a clean, centrally auditable authorization matrix for all slash commands.

5. **Deduplication Hashing** — `mcp/src/models/schemas.py` `compute_dedup_hash` uses SHA-256 over `rule_id:file_path:message` — a deterministic and collision-resistant approach to finding deduplication.

6. **Approval Audit Trail** — `mcp/src/models/entities.py` stores `approved_by`, `approved_at`, `revoked_by`, `revoked_at` with justification text, enabling a full approval history without a separate audit log table.

7. **Structured Pydantic Settings** — `mcp/src/core/config.py` uses `pydantic-settings` for configuration, ensuring type coercion and `.env` support with a single, auditable source of truth for all configuration variables.

---

*Concerns audit: 2026-04-28*

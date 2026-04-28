# Testing Patterns

**Analysis Date:** 2026-04-28

## Test Framework

**Python (MCP backend) — pytest:**
- Runner: `pytest` >= 7.0.0
- Async support: `pytest-asyncio` >= 0.23.0 with `asyncio_mode = auto` (set in `mcp/pytest.ini`)
- HTTP test client: `httpx.AsyncClient` with `ASGITransport` (ASGI-level, no network)
- Config: `mcp/pytest.ini`
  ```ini
  [pytest]
  asyncio_mode = auto
  pythonpath = .
  ```

**TypeScript (Dashboard) — Playwright:**
- Runner: `@playwright/test` ^1.59.1
- Type: E2E browser tests only (no unit/integration tests for frontend)
- Config: `dashboard/playwright.config.ts`
- Browser: Chromium (Desktop Chrome profile)
- Timeout: 30s per test, 10s for `expect`
- Parallelism: `fullyParallel: false`

**Run Commands:**
```bash
# Python unit + integration tests
cd mcp && python -m pytest

# Python tests with verbose output
cd mcp && python -m pytest -v

# Python specific test file
cd mcp && python -m pytest tests/test_chat_api.py

# Dashboard E2E tests (starts both backend + frontend automatically)
cd dashboard && npm run test:e2e

# Dashboard E2E with Playwright UI
cd dashboard && npm run test:e2e:ui
```

## Test File Organization

**Python (`mcp/tests/`):**
- Location: all tests in `mcp/tests/` directory (separate from `mcp/src/`)
- Naming: `test_<subject>.py` — subject matches module being tested
- Shared fixtures: `mcp/tests/conftest.py`
- `mcp/tests/__init__.py` is present (makes `tests` a package)

**Dashboard (`dashboard/tests/e2e/`):**
- Directory defined in `playwright.config.ts` as `testDir: './tests/e2e'`
- No E2E test files found in current codebase (directory empty or missing)
- Playwright config is fully wired for E2E test execution

**Test file → module mapping:**
| Test file | Module tested |
|-----------|--------------|
| `test_api_integration.py` | `src/api/artifacts.py` — full API integration via HTTP client |
| `test_chat_api.py` | `src/api/chat.py` — ChatOps command auth and business logic |
| `test_db.py` | `src/models/entities.py` — ORM model creation and persistence |
| `test_e2e.py` | `src/services/processor.py` — full pipeline end-to-end |
| `test_enricher.py` | `src/services/enricher.py` |
| `test_github_client.py` | `src/services/github_client.py` |
| `test_guardrails_injection.py` | `src/core/guardrails.py` — InjectionGuardrail |
| `test_guardrails_scrubbing.py` | `src/core/guardrails.py` — ScrubbingService |
| `test_llm_api.py` | `src/api/analysis.py` — /findings/{id}/explain endpoint |
| `test_llm_client.py` | `src/services/llm/client.py` |
| `test_llm_schemas.py` | `src/services/llm/schemas.py` |
| `test_llm_service.py` | `src/services/llm/service.py` |
| `test_main.py` | `src/main.py` — app startup, health endpoint |
| `test_normalizer.py` | `src/services/normalizer.py` |
| `test_poller.py` | `src/services/poller.py` |
| `test_processor.py` | `src/services/processor.py` — unit-level |
| `test_schemas.py` | `src/models/schemas.py` |

## Test Types Present

**Unit Tests (pure function/class testing):**
- `test_guardrails_injection.py` — tests `InjectionGuardrail.check()` and `.sanitize()` with parametrize
- `test_guardrails_scrubbing.py` — tests `ScrubbingService.scrub_content()`
- `test_normalizer.py` — tests each `*Normalizer` class with raw input strings
- `test_llm_service.py` — tests `LLMAnalysisService` with mocked `GeminiClient`
- `test_schemas.py` — tests `compute_dedup_hash` and Pydantic model validation
- `test_enricher.py` — tests `DataEnricher.enrich()` with known CWE → CVSS mappings

**Integration Tests (in-process HTTP via ASGITransport):**
- `test_api_integration.py` — POST /projects, POST /artifacts/process, GET /github/runs, webhooks, GET /findings
- `test_chat_api.py` — auth token endpoint, all /api/chat/command variants, role enforcement
- `test_llm_api.py` — GET /findings/{id}/explain with dependency override
- `test_db.py` — SQLAlchemy model creation against in-memory SQLite
- `test_poller.py` — poller logic with mocked GitHub client and processor

**End-to-End (pipeline) Tests:**
- `test_e2e.py` — full `fetch → scrub → normalize → enrich → DB storage` pipeline using `SecurityProcessor` with mocked GitHub client and real SQLite in-memory DB
  - Tests SARIF findings storage, CVSS enrichment, email scrubbing, SpotBugs XML processing

**Browser E2E (Playwright):**
- Infrastructure present in `dashboard/playwright.config.ts`
- Starts backend (`TEST_MODE=1`, SQLite in-memory) on port 8001
- Starts frontend (`VITE_API_URL=http://localhost:8001`) on port 5174
- No actual `.spec.ts` test files written yet

## Coverage

**Requirements:** No configured coverage target or `pytest-cov` plugin detected in `requirements.txt`

**Estimated coverage by area:**
- API routes: high — `test_api_integration.py` + `test_chat_api.py` cover all major endpoints
- Business logic pipeline: high — `test_e2e.py` covers the full processor chain
- Guardrails: high — both injection and scrubbing tested exhaustively
- Normalizers: high — all normalizer classes tested with sample payloads
- LLM service: high — mocked client, tests analyze/save flow
- Poller: medium — basic poll flow tested, edge cases partial
- DB models: medium — creation and FK relationships tested
- Dashboard TypeScript: none — no unit/component tests present

**View Coverage:**
```bash
# Install coverage support first
pip install pytest-cov

# Then run with coverage
cd mcp && python -m pytest --cov=src --cov-report=html
# Report at: mcp/htmlcov/index.html
```

## Test Data

**Fixtures (conftest.py — `mcp/tests/conftest.py`):**

```python
@pytest_asyncio.fixture
async def client():
    # Fresh schema per test via drop_all + create_all
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest_asyncio.fixture
async def project(client):
    # Creates a real project via POST /projects
    resp = await client.post("/projects", json={
        "name": f"Java App {uuid.uuid4().hex[:8]}",
        "github_url": f"https://github.com/test/{uuid.uuid4().hex}",
    })
    return resp.json()
```

**Per-test local fixtures:**
- `test_db.py` and `test_e2e.py` each define their own `db_session`/`db` fixture using isolated in-memory SQLite
- `test_chat_api.py` defines a `finding_id` fixture that directly inserts Project → Artifact → Finding via `AsyncSessionLocal`
- `test_poller.py` defines its own `db` fixture following the same pattern

**Mocking approach:**
- `unittest.mock.AsyncMock` for async service dependencies (GitHub client, SecurityProcessor, LLMAnalysisService)
- `unittest.mock.MagicMock` for synchronous objects (Finding ORM mock in `test_llm_service.py`)
- `unittest.mock.patch` for settings and module-level dependencies
- FastAPI dependency overrides for HTTP-level mocking:
  ```python
  app.dependency_overrides[get_github_client] = lambda: mock_gh
  try:
      resp = await client.get("/github/runs")
  finally:
      app.dependency_overrides.pop(get_github_client, None)
  ```

**Inline raw test data:**
- SARIF JSON constructed as string literals in `test_normalizer.py` and `test_e2e.py`
- SpotBugs XML constructed as multiline strings in `test_e2e.py`
- No separate fixture files (no `fixtures/` or `factories/` directory)

## Test Structure

**Suite organization pattern:**
```python
# Docstring at top for phase/context labeling
"""Tests for Phase 6: ChatOps command API and auth."""

# Helper factories (non-fixture)
def _token(role: str = "developer") -> str: ...
def _headers(role: str = "developer") -> dict: ...

# Dashes-comment section headers group related tests
# ---------------------------------------------------------------------------
# Auth — demo login
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_<action>_<expected_outcome>(client):
    resp = await client.post("/endpoint", json={...}, headers=...)
    assert resp.status_code == 200
    body = resp.json()
    assert body["field"] == expected_value
```

**Naming convention:** `test_<subject>_<condition>_<result>` — e.g.:
- `test_approve_finding`
- `test_approve_already_approved`
- `test_approve_short_justification`
- `test_approve_nonexistent_finding`
- `test_demo_login_invalid_role`
- `test_command_no_token_returns_401`

**Parametrize usage:**
```python
@pytest.mark.parametrize("bad_input", [
    "<script>alert(1)</script>",
    "Ignore all previous instructions...",
    ...
])
def test_check_rejects_injection_patterns(guardrail, bad_input):
    is_safe, reason = guardrail.check(bad_input)
    assert not is_safe
```
Used in `test_guardrails_injection.py` for exhaustive injection pattern coverage.

**Async test marker:**
- All async tests use `@pytest.mark.asyncio` explicitly (even with `asyncio_mode = auto`)
- Sync tests (schema validation, unit logic) have no mark — run as plain functions

## Playwright E2E Setup

The backend is started in `TEST_MODE=1` which activates:
- SQLite in-memory database
- `/test/reset` endpoint — clears all data between tests
- `/test/inject-finding` endpoint — inserts test findings directly

This is wired in `mcp/src/main.py` and consumed by Playwright `beforeEach` to ensure a clean state per test run.

---

*Testing analysis: 2026-04-28*

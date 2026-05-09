# Testing — chat-system

> Toàn bộ chiến lược test, cách chạy, cách viết thêm. Cập nhật cuối Day 7 (2026-05-14).

---

## Tổng quan

| Layer | Tool | Số case | Run command |
|---|---|---|---|
| Backend unit + integration | pytest + pytest-asyncio | **200** | `pytest tests/ -q` |
| Backend smoke (live API) | stdlib urllib | 7 endpoints | `python -m scripts.smoke_test` |
| Frontend E2E | Playwright | 2 spec | `npm run test:e2e` |
| AI guardrails | pytest (subset) | 24 (gộp trong 200) | `pytest tests/test_guardrails_*.py -v` |
| Type check FE | TypeScript `tsc -b` | toàn project | `npm run build` |

Total automated: **209 case + type check**. Manual UAT theo `docs/demo-script.md`.

---

## Backend — pytest

### Cấu hình

`mcp/pytest.ini`:
```ini
[pytest]
asyncio_mode = auto       # auto-detect async tests, không cần @pytest.mark.asyncio
pythonpath = .            # cho phép `from src.X import Y` không cần install package
```

`mcp/tests/conftest.py` cung cấp:
- In-memory SQLite engine + StaticPool (test isolation)
- AsyncMock cho GitHubClient, LLM client, Gemini API
- Test client cho FastAPI (TestClient với DI override)
- `TEST_MODE=1` env → bật `/test/reset` + `/test/inject-finding` endpoints (chỉ active khi test)

### Phân nhóm 200 test

| File | Số case | Phạm vi |
|---|---|---|
| `test_normalizer.py` | 45 | SARIF/XML/JSON parser cho 6 SAST tool, dedup hash, severity mapping, lenient parsing edge cases |
| `test_enricher.py` | 17 | CWE description lookup, CVSS score parsing, OWASP Top 10 2021 mapping, `cwe2`/`cvss` lib quirks |
| `test_guardrails_injection.py` | 17 | 9 injection pattern reject + sanitize control chars + length cap 2000 chars |
| `test_github_client.py` | 15 | List runs/artifacts, fetch artifact (zip slip + zip bomb protection), dispatch_workflow, rerun_workflow |
| `test_chat_api.py` | 14 | 7 ChatOps commands + free-form chat + JWT auth + role validation |
| `test_api_integration.py` | 14 | End-to-end POST /artifacts/process → GET /findings flow, webhook auth, project create/list |
| `test_llm_service.py` | 11 | Prompt build + Gemini call mock + AnalysisResult validation + retry logic |
| `test_guardrails_scrubbing.py` | 7 | detect-secrets line replacement + email/IP regex |
| `test_config_api.py` | 7 | Runtime config CRUD (sast_tools / gates / ai keys) |
| `test_poller.py` | 6 | Poller iterate runs, skip processed, idempotent project creation, error continuation |
| `test_llm_schemas.py` | 6 | AnalysisResult Pydantic validation, structured JSON shape |
| `test_stats_api.py` | 5 | Overview KPI, latest_scan, runs trend |
| `test_schemas.py` | 5 | FindingCreate, dedup hash determinism + uniqueness |
| `test_processor.py` | 5 | End-to-end fetch → scrub → normalize → enrich → store with mocks |
| `test_pagination.py` | 5 | `/findings` skip/limit + X-Total-Count header + filter combo |
| `test_llm_client.py` | 5 | Gemini SDK wrapper retry on 429/503, structured output JSON parse |
| `test_e2e.py` | 4 | TEST_MODE-only `/test/reset` + `/test/inject-finding` smoke |
| `test_main.py` | 3 | App boot, healthz, OpenAPI spec |
| `test_llm_api.py` | 3 | `/findings/{id}/explain` happy path + error |
| `test_delete_project.py` | 3 | Cascade delete project → artifacts → findings |
| `test_db.py` | 3 | Engine boot, Base.metadata.create_all idempotent |

**Total: 200 case.** Time: ~18-20 giây trên Windows local.

### Run

```powershell
cd D:\School\DoAnTotNghiep\chat-system\mcp
.venv\Scripts\activate

# Toàn bộ
pytest tests/ -q

# Verbose 1 file
pytest tests/test_normalizer.py -v

# Filter pattern
pytest tests/ -k "guardrails" -v

# Stop sau test fail đầu tiên
pytest tests/ -x

# Hiện stdout (debug print)
pytest tests/ -s
```

### Coverage

Hiện không enforce % coverage. Đo thủ công:
```powershell
pip install pytest-cov
pytest tests/ --cov=src --cov-report=html
# Mở htmlcov/index.html
```

Coverage backend hiện ~85% (estimate, services/normalizer 100%, llm 75% do mock).

---

## Backend — Smoke test (live)

`mcp/scripts/smoke_test.py` — kiểm tra 7 endpoint khi backend đang chạy. Không cần Gemini quota.

### Run

```powershell
# Backend phải chạy (uvicorn) trước
cd D:\School\DoAnTotNghiep\chat-system\mcp
.venv\Scripts\python -m scripts.smoke_test

# Test against remote / docker
.venv\Scripts\python -m scripts.smoke_test --base http://localhost:8000
.venv\Scripts\python -m scripts.smoke_test --base https://abc-123.ngrok-free.app
```

### Output

```
=== Smoke test against http://localhost:8000 ===

  [OK]  health                            OK
  [OK]  swagger                           OK
  [OK]  projects.list                     OK
  [OK]  stats.overview                    OK
  [OK]  findings.list                     OK
  [OK]  integration endpoint              OK
  [OK]  webhook reachable                 OK

7/7 passed
```

Exit code: 0 = all pass, 1 = any fail. Thích hợp cho pre-demo automation.

---

## Frontend — Playwright E2E

`dashboard/tests/e2e/` — 2 spec hiện tại:

- `debug.spec.ts` — visit dashboard, screenshot mỗi page, dùng debug nhanh
- `interactions.spec.ts` — flow ChatOps + approval dialog (smoke flow)

### Run

```powershell
cd D:\School\DoAnTotNghiep\chat-system\dashboard

# Headless
npm run test:e2e

# Interactive UI mode (debug)
npm run test:e2e:ui

# Single spec
npx playwright test tests/e2e/interactions.spec.ts

# Update screenshots
npx playwright test --update-snapshots
```

### Yêu cầu

Backend phải chạy ở `TEST_MODE=1` để E2E có thể inject finding qua `/test/inject-finding`:

```powershell
# Terminal 1
$env:TEST_MODE="1"
cd D:\School\DoAnTotNghiep\chat-system\mcp
uvicorn src.main:app --port 8000

# Terminal 2
cd D:\School\DoAnTotNghiep\chat-system\dashboard
npm run dev

# Terminal 3
npm run test:e2e
```

### Configuration

`dashboard/playwright.config.ts`:
- `baseURL: http://localhost:5173` (Vite dev)
- Browsers: Chromium (chỉ run 1 browser cho speed)
- Retries: 0 local, 2 trên CI
- Timeout: 30s per test

---

## Frontend — Type check

`tsc -b` strict mode (không chỉ noEmit). Bắt cả unused-locals/imports.

```powershell
cd D:\School\DoAnTotNghiep\chat-system\dashboard
npm run build           # tsc -b && vite build
# hoặc
npx tsc -b
```

Pass = exit 0, output `dist/` có file. Bundle hiện 305 KB JS / 86 KB gzip.

---

## CI integration

Hiện chưa có CI tự động cho chat-system repo. Recommend (post-thesis):

```yaml
# .github/workflows/ci.yml (đề xuất)
jobs:
  backend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.13' }
      - run: pip install -r mcp/requirements.txt
      - run: cd mcp && pytest tests/ -q --cov=src
  
  frontend-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: cd dashboard && npm ci
      - run: cd dashboard && npm run build
  
  e2e:
    needs: [backend-tests, frontend-build]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.13' }
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: pip install -r mcp/requirements.txt
      - run: cd dashboard && npm ci && npx playwright install
      - name: Start backend
        run: |
          cd mcp
          TEST_MODE=1 uvicorn src.main:app --port 8000 &
          sleep 5
      - name: Start frontend
        run: |
          cd dashboard
          npm run dev &
          sleep 5
      - run: cd dashboard && npm run test:e2e
```

---

## Manual UAT (User Acceptance Test)

Theo `docs/demo-script.md` 8 phần. Kiểm tra checklist:

| # | Test case | Expected |
|---|---|---|
| 1 | Mở dashboard, click 7 tab | Mọi tab load không error console |
| 2 | Login Chat tab role=security_lead | Token được set, `/api/chat/auth/me` trả 200 |
| 3 | `/scan` từ Chat | GitHub Actions repo target có run mới `queued`/`in_progress` |
| 4 | Chờ CI xong, đợi poll 5 phút | Pipelines tab có run mới với severity summary |
| 5 | Vulnerabilities → click 1 finding → Ask AI | AI panel render Vietnamese explain + Unified Diff |
| 6 | `/approve <id>` với reason ≥ 20 chars | Finding status → APPROVED, audit trail có user + time |
| 7 | `/approve <id>` lại | 409 "đã approve rồi" |
| 8 | `/approve <id>` reason < 20 chars | 422 validation error |
| 9 | Dependencies tab | Group theo package, severity floor mặc định ≥ high |
| 10 | Free-form chat "phân tích finding 5" | AI trả lời + chip "Run /explain 5" |
| 11 | `/report` | HTML download, mở browser tab mới |

---

## Edge case test backlog (chưa cover, cho V2)

- Concurrent webhook (race condition khi 2 run cùng POST)
- DB lock SQLite under high concurrency
- Gemini quota exhaustion mid-batch
- ngrok URL change while CI running
- Project soft-delete + restore
- Multi-tenant Gemini key isolation
- Audit trail export (CSV/PDF)
- Composite Action gateway down → CI passes nhưng warning visible

---

## Adding a new test

### Backend (pytest)

1. File: `mcp/tests/test_<module>.py`
2. Async function:
   ```python
   import pytest
   
   async def test_finding_dedup_hash_stable():
       from src.models.schemas import compute_dedup_hash
       h1 = compute_dedup_hash("R1", "/a.py", "msg")
       h2 = compute_dedup_hash("R1", "/a.py", "msg")
       assert h1 == h2
   ```
3. Run: `pytest tests/test_<module>.py::test_finding_dedup_hash_stable -v`
4. Trước commit: `pytest tests/ -q` toàn bộ pass

### Frontend (Playwright)

1. File: `dashboard/tests/e2e/<feature>.spec.ts`
2. Spec:
   ```ts
   import { test, expect } from '@playwright/test';
   
   test('SCA tab loads grouped dependencies', async ({ page }) => {
     await page.goto('/');
     await page.click('text=Dependencies');
     await expect(page.locator('[data-testid=dep-pkg-row]')).toHaveCount(1, { timeout: 5000 });
   });
   ```
3. Run: `npx playwright test tests/e2e/<feature>.spec.ts --headed`

### Smoke (urllib)

1. Edit `mcp/scripts/smoke_test.py`
2. Add `Check("<name>", check_<fn>)` vào list
3. Implement `check_<fn>(base) -> Any`, raise on failure

---

## Test data fixtures

`mcp/tests/conftest.py` cung cấp:

| Fixture | Mục đích |
|---|---|
| `db_session` | Fresh in-memory SQLite per test |
| `client` | FastAPI TestClient với DB override |
| `mock_github` | AsyncMock GitHubClient |
| `mock_llm` | AsyncMock Gemini service |
| `auth_token_developer` | JWT role=developer |
| `auth_token_security_lead` | JWT role=security_lead |
| `auth_token_admin` | JWT role=admin |
| `sample_finding` | Finding row với severity=high |
| `sample_run_artifacts` | Mock GitHub artifacts dict |

Reuse các fixture này thay vì setup state thủ công trong test.

---

## Known testing gaps

- **Multi-tenant runtime**: tests/test_poller.py vẫn test single-tenant (đã revert ở Day 2). Khi flip-on multi-tenant runtime sang v0.2, viết lại test_poller.py + add test_multi_project.py.
- **Container scan size cap**: chưa test artifact > 50 MB (Trivy image scan có thể vượt giới hạn `_MAX_ZIP_BYTES`).
- **Composite Action**: chưa test live trên ALOUTE (user-side Day 8 task).
- **i18n**: AI prompt hardcode tiếng Việt, chưa có test bilingual.

---

## Cheat-sheet — chạy nhanh

```powershell
# 1. Backend tests (~20s)
cd mcp; .venv\Scripts\python -m pytest tests/ -q

# 2. Frontend type check + build (~5s)
cd dashboard; npm run build

# 3. Smoke test live (~3s, cần backend running)
cd mcp; .venv\Scripts\python -m scripts.smoke_test

# 4. E2E Playwright (~30s, cần backend + frontend running)
cd dashboard; npm run test:e2e

# 5. Toàn bộ — preflight script
.venv\Scripts\python -m pytest tests/ -q && cd ../dashboard && npm run build && cd ../mcp && .venv\Scripts\python -m scripts.smoke_test
```

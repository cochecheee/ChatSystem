# Phase 02: Pipeline Visibility - Pattern Map

**Mapped:** 2026-04-29
**Files analyzed:** 5
**Analogs found:** 5 / 5

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `dashboard/src/api/client.ts` | utility | request-response | `dashboard/src/api/client.ts` (self — signature change only) | exact |
| `dashboard/src/pages/Pipelines.tsx` | component | CRUD + event-driven | `dashboard/src/pages/Pipelines.tsx` (self — extend in-place) | exact |
| `dashboard/src/types/index.ts` | config | transform | `dashboard/src/types/index.ts` (self — add optional field) | exact |
| `mcp/tests/test_main.py` | test | request-response | `mcp/tests/test_main.py` (self) + `mcp/tests/test_github_client.py` (mock pattern) | exact |
| `mcp/tests/test_github_client.py` | test | request-response | `mcp/tests/test_github_client.py` (self — add test stub) | exact |

---

## Pattern Assignments

### `dashboard/src/api/client.ts` (utility, request-response)

**Analog:** `dashboard/src/api/client.ts` (self)

**Current signature to replace** (lines 53–54):
```typescript
runs: (status = 'completed') =>
  get<WorkflowRun[]>('/github/runs', { status }),
```

**Required replacement** — remove hardcoded status, thread optional branch param:
```typescript
runs: (branch?: string) =>
  get<WorkflowRun[]>('/github/runs', branch ? { branch } : {}),
```

**Caller sites to update** — all three `api.github.runs()` calls in `Pipelines.tsx` (lines 377, 400, 417) currently pass no argument. After the signature change they remain valid as-is (no argument = no branch filter = all statuses). The `setInterval` silent-poll call at line 417 also needs no change.

**Import pattern** (lines 1, 19–25 — no changes needed):
```typescript
import type { ..., WorkflowRun } from '../types';

async function get<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const url = new URL(BASE + path);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)));
  const res = await fetch(url.toString(), { headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}
```

Note: `get<T>` accepts `Record<string, string | number>` — passing `{ branch }` where branch is `string` is type-safe. Passing an empty object `{}` when branch is undefined produces no query params, which is the correct behavior: the backend `GET /github/runs` defaults `status=""` via no param, and `github_client.py` line 44 only adds `status` to params `if status:`, so omitting it returns all statuses.

---

### `dashboard/src/types/index.ts` (config, transform)

**Analog:** `dashboard/src/types/index.ts` (self)

**Current `WorkflowRun` interface** (lines 32–42):
```typescript
export interface WorkflowRun {
  id: number;
  name: string;
  conclusion: string | null;
  status: string;
  created_at: string;
  head_branch: string;
  head_sha: string;
  run_number: number;
  html_url?: string;
}
```

**Required addition** — append `updated_at` as optional field:
```typescript
export interface WorkflowRun {
  id: number;
  name: string;
  conclusion: string | null;
  status: string;
  created_at: string;
  updated_at?: string;   // ADD: GitHub API field; used for duration calculation in RunSummaryStrip
  head_branch: string;
  head_sha: string;
  run_number: number;
  html_url?: string;
}
```

**Placement:** Insert `updated_at?: string;` after `created_at: string;` (after line 36). No other changes to the file.

---

### `dashboard/src/pages/Pipelines.tsx` (component, CRUD + event-driven)

**Analog:** `dashboard/src/pages/Pipelines.tsx` (self — all additions are inline extensions)

#### Imports pattern (lines 1–5 — add `AreaTrend`, `SeverityBar`):
```typescript
import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { AreaTrend, SeverityBar } from '../components/Charts';   // ADD
import { Icon } from '../components/Icon';
import type { Finding, WorkflowArtifact, WorkflowRun } from '../types';
import { SEVERITY_ORDER } from '../types';
```

#### Branch filter state + derived lists (add after line 424 — after `selected` computation):
```typescript
// PIPE-02: branch filter state
const [branch, setBranch] = useState<string>('all');

const branchOptions = useMemo(
  () => [...new Set(runs.map(r => r.head_branch))].sort(),
  [runs],
);

const filteredRuns = useMemo(() => {
  if (branch === 'all') return runs;
  return runs.filter(r => r.head_branch === branch);
}, [runs, branch]);

// Split filteredRuns into CI/CD buckets (replaces existing ciRuns/cdRuns which use `runs`)
// IMPORTANT: stats and trend always use unfiltered `runs`; list sections use filteredRuns
const { ciRuns, cdRuns } = useMemo(() => {
  const ci: WorkflowRun[] = [];
  const cd: WorkflowRun[] = [];
  for (const r of filteredRuns) {
    (categorizeRun(r) === 'cd' ? cd : ci).push(r);
  }
  return { ciRuns: ci, cdRuns: cd };
}, [filteredRuns]);
```

Note: The existing `ciRuns`/`cdRuns` derivation at lines 434–441 uses `runs` directly. Replace its body to use `filteredRuns` instead, but keep `stats` at lines 426–431 pointing at unfiltered `runs`.

#### LiveIndicator (add to page header JSX, adjacent to Refresh button, line ~479):
```tsx
// PIPE-03: derive from unfiltered runs
const hasInProgress = runs.some(r => r.status === 'in_progress');

// In page header right-side flex div, after Refresh button:
{hasInProgress && (
  <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
    <div style={{
      width: 6, height: 6, borderRadius: '50%',
      background: 'var(--accent)',
      animation: 'pulse 1.5s ease-in-out infinite',
    }} />
    <span style={{ fontSize: 'var(--ts-xs)', fontWeight: 600, color: 'var(--fg-3)' }}>
      Live
    </span>
  </div>
)}
```

#### Branch filter `<select>` (add inside page header, before h1 group or as first child of header flex):
```tsx
// PIPE-02: branch filter select
<div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
  <Icon name="branch" size={11} style={{ color: 'var(--fg-3)' }} />
  <select
    className="filter-toolbar select"
    style={{ maxWidth: 140 }}
    value={branch}
    onChange={e => setBranch(e.target.value)}
  >
    <option value="all">All branches</option>
    {branchOptions.map(b => <option key={b} value={b}>{b}</option>)}
  </select>
</div>
```

#### Page sub-heading copy update (line 477 — existing):
```tsx
// BEFORE (line 477):
<div className="sub">GitHub Actions · {runs.length} recent runs</div>

// AFTER (show filtered count when branch active):
<div className="sub">
  GitHub Actions · {branch === 'all'
    ? `${runs.length} recent runs`
    : `${filteredRuns.length} of ${runs.length} runs`}
</div>
```

#### KPI fontWeight fix (lines 488–499 — fix 700 → 600):
```tsx
// BEFORE (4 occurrences, e.g. line 488):
<div style={{ fontSize: 18, fontWeight: 700 }}>{stats.total}</div>

// AFTER (correct per UI-SPEC §Typography — no weight 700 permitted):
<div style={{ fontSize: 18, fontWeight: 600 }}>{stats.total}</div>
```
Apply to all 4 KPI value divs (lines 488, 492, 495, 499).

#### TrendCard + trendData (PIPE-04 — add to detail panel right pane, before `RunPanel`):
```tsx
// Trend data computed from unfiltered runs (always, per anti-pattern note)
const trendData = useMemo(() => {
  const sorted = [...runs]
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    .slice(-30);
  return {
    failed: sorted.map(r => r.conclusion === 'failure' ? 1 : 0),
    passed: sorted.map(r => r.conclusion === 'success' ? 1 : 0),
  };
}, [runs]);

// In the detail panel JSX, wrapping RunPanel (line ~537):
<div style={{ flex: 1, minWidth: 0, overflowY: 'auto' }}>
  {/* TrendCard — only when >= 2 runs (guards AreaTrend stepX division by zero) */}
  {runs.length >= 2 && (
    <div className="card" style={{ marginBottom: 14, margin: '14px 14px 0' }}>
      <div className="card-header">
        <div className="h3">Pipeline Trend</div>
        <span className="muted" style={{ fontSize: 'var(--ts-sm)' }}>
          Pass / fail over last 30 runs
        </span>
      </div>
      <div className="card-pad">
        <AreaTrend values={trendData.failed} values2={trendData.passed} height={120} />
      </div>
    </div>
  )}

  {selected ? (
    <RunPanel key={selected.id} run={selected} />
  ) : (
    <div className="empty" style={{ marginTop: 80 }}>
      {loading ? 'Loading…' : 'Select a pipeline run to view results'}
    </div>
  )}
</div>
```

#### RunSummaryStrip (PIPE-05 — add duration helper + strip sub-render to `renderRunRow`):
```tsx
// Duration helper (add near other pure functions, e.g. after timeAgo):
function formatDuration(run: WorkflowRun): string {
  if (!run.updated_at || !run.created_at) return '—';
  const ms = new Date(run.updated_at).getTime() - new Date(run.created_at).getTime();
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  if (h > 0) return `${h}h ${m % 60}m`;
  return `${m}m ${s % 60}s`;
}

// In renderRunRow, after the existing 3 rows and only for the selected run:
// (Artifacts/findings for the selected run are already in RunPanel state;
//  for Phase 02 the strip uses only the run object data available in the list)
// The tool tags require artifact state — show strip only for selected run.
// For non-selected rows: strip is omitted (no extra API calls).
{r.id === selectedId && (
  <>
    <div style={{ borderTop: '1px solid var(--line)', margin: '6px 0' }} />
    {/* Tool tags: only shown if we have artifact data — deferred to RunPanel context */}
    {/* Severity bar: zero-count case renders muted bar automatically via SeverityBar */}
    <SeverityBar counts={{ critical: 0, high: 0, medium: 0, low: 0 }} height={4} />
    <div style={{ display: 'flex', gap: 8, marginTop: 4, fontSize: 'var(--ts-xs)', color: 'var(--fg-3)', alignItems: 'center' }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
        <Icon name="clock" size={10} />
        <span className="mono">{formatDuration(r)}</span>
      </span>
    </div>
  </>
)}
```

#### Vietnamese copy replacements (exact line targets from RESEARCH.md Pitfall 5):

| Location | Before | After |
|----------|--------|-------|
| Line 251 (`handleReprocess` confirm) | `` `Xoá findings cũ và xử lý lại run #${run.run_number}?` `` | `` `Delete old findings and reprocess run #${run.run_number}?` `` |
| Line 256 (reprocess success msg) | `` `Đang xử lý ${res.deleted_artifacts} artifact cũ…` `` | `` `Reprocessing ${res.deleted_artifacts} artifacts — results will update in ~10s…` `` |
| Line 259 (reprocess error) | `` `Lỗi: ${e}` `` | `` `Reprocess failed: ${e}` `` |
| Line 282 (reprocess button label) | `'Đang xử lý…'` | `'Reprocessing…'` |
| Line 299 (findings loading) | `'Đang tải kết quả scan…'` | `'Loading scan results…'` |
| Lines 306–308 (empty findings text) | Vietnamese no-findings message | `'No findings for this run.'` + sub `'Artifacts may have expired (retention: 1 day) or CI has not triggered a webhook.'` |
| Line 543 (detail panel empty — loading) | `'Đang tải…'` | `'Loading…'` |
| Line 543 (detail panel empty — no selection) | `'Chọn một pipeline run để xem kết quả'` | `'Select a pipeline run to view results'` |

#### Existing polling calls — update signature (lines 377, 400, 417):
```typescript
// BEFORE (all 3 call sites):
api.github.runs()

// AFTER — no change needed to the call sites; new signature `runs(branch?: string)`
// with no argument still works correctly and fetches all runs (no status filter).
// The branch filter is a client-side useMemo — no branch param is sent to the API.
api.github.runs()
```

---

### `mcp/tests/test_main.py` (test, request-response)

**Analog:** `mcp/tests/test_main.py` (self) — follows `@pytest.mark.asyncio` + `client` fixture pattern from conftest.py

**Existing test pattern** (lines 4–8 — copy this structure exactly):
```python
@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
```

**conftest `client` fixture** (conftest.py lines 15–22 — used automatically, no import needed):
```python
@pytest_asyncio.fixture
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

**Test stubs to add for PIPE-01 and PIPE-03** (append to `test_main.py`):
```python
# ---------------------------------------------------------------------------
# Tests: GET /github/runs (PIPE-01, PIPE-03)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_github_runs_all_statuses(client):
    """PIPE-01/PIPE-03: /github/runs must NOT pass status=completed to GitHub.

    Patches GitHubClient.list_workflow_runs to assert it is called with
    status="" (empty string) so in_progress runs are included.
    """
    from unittest.mock import AsyncMock, patch

    mock_runs = [
        {"id": 1, "name": "CI", "status": "completed", "conclusion": "success",
         "head_branch": "main", "head_sha": "abc1234", "run_number": 1,
         "created_at": "2026-04-29T00:00:00Z", "html_url": "https://github.com"},
        {"id": 2, "name": "CI", "status": "in_progress", "conclusion": None,
         "head_branch": "main", "head_sha": "def5678", "run_number": 2,
         "created_at": "2026-04-29T01:00:00Z", "html_url": "https://github.com"},
    ]

    with patch(
        "src.api.artifacts.GitHubClient.list_workflow_runs",
        new_callable=AsyncMock,
        return_value=mock_runs,
    ) as mock_list:
        response = await client.get("/github/runs")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    statuses = {r["status"] for r in data}
    assert "in_progress" in statuses, "in_progress runs must be included (PIPE-03)"

    # Verify the backend did NOT pass status='completed' — it should pass status=""
    call_kwargs = mock_list.call_args.kwargs if mock_list.call_args.kwargs else {}
    call_args = mock_list.call_args.args if mock_list.call_args else ()
    # list_workflow_runs signature: (workflow_name, branch, status)
    # status must be "" (falsy) so github_client skips adding it to params
    passed_status = call_kwargs.get("status", call_args[2] if len(call_args) > 2 else "")
    assert passed_status == "", (
        f"Backend must call list_workflow_runs with status='' not '{passed_status}'"
    )
```

Note: The backend route `GET /github/runs` in `artifacts.py` lines 80–95 has `status: str = "completed"` as the default FastAPI query param. PIPE-01/03 requires changing this default to `""`. The test above exercises the endpoint with no `?status=` query param, so it will catch the default value regression.

---

### `mcp/tests/test_github_client.py` (test, request-response)

**Analog:** `mcp/tests/test_github_client.py` (self) — follows `_mock_client` helper + `patch` context manager pattern

**Existing mock infrastructure** (lines 23–33 — reuse these helpers exactly):
```python
def _mock_client(response_content: bytes | None = None, json_data: dict | None = None):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.content = response_content or b""
    mock_resp.json.return_value = json_data or {}

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.get = AsyncMock(return_value=mock_resp)
    return mock_http
```

**Test stub to add for PIPE-02** (append to `test_github_client.py`):
```python
# ---------------------------------------------------------------------------
# Tests: branch filter param (PIPE-02)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_branch_filter_param():
    """PIPE-02: list_workflow_runs must forward the branch param to GitHub API."""
    runs = [
        {"name": "CI", "id": 10, "head_branch": "feature/x"},
        {"name": "CI", "id": 11, "head_branch": "main"},
    ]
    mock_http = _mock_client(json_data={"workflow_runs": runs})

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http) as mock_cls:
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        result = await client.list_workflow_runs(workflow_name="", branch="feature/x", status="")

    # Verify branch was passed as a query param to the GitHub API call
    mock_http.get.assert_called_once()
    call_kwargs = mock_http.get.call_args.kwargs
    assert "params" in call_kwargs, "branch must be passed via params dict"
    assert call_kwargs["params"].get("branch") == "feature/x"

    # Verify status was NOT added to params when empty (github_client.py line 44: `if status:`)
    assert "status" not in call_kwargs["params"], (
        "status must not appear in GitHub API params when empty string passed"
    )


@pytest.mark.asyncio
async def test_no_status_param_when_empty():
    """PIPE-01/PIPE-03: When status='' is passed, GitHub API params must not include status."""
    mock_http = _mock_client(json_data={"workflow_runs": []})

    with patch("src.services.github_client.httpx.AsyncClient", return_value=mock_http):
        client = GitHubClient(token="tok", owner="owner", repo="repo")
        await client.list_workflow_runs(workflow_name="", branch="", status="")

    call_kwargs = mock_http.get.call_args.kwargs
    assert "status" not in call_kwargs.get("params", {}), (
        "Empty status must not be forwarded to GitHub API"
    )
```

---

## Shared Patterns

### State + useMemo derivation pattern (Pipelines.tsx)

**Source:** `dashboard/src/pages/Pipelines.tsx` lines 426–441 (existing `stats` and `ciRuns`/`cdRuns` memos)
**Apply to:** Branch filter state, filteredRuns, trendData — all follow the same `useMemo([runs, ...])` pattern

```typescript
// Canonical pattern for derived state in Pipelines.tsx:
const derivedValue = useMemo(() => {
  // pure computation from runs or filteredRuns
}, [runs]);  // or [runs, branch] when branch-dependent
```

**Rule:** `stats` and `trendData` always depend on `[runs]`. `filteredRuns`, `branchOptions`, and `ciRuns`/`cdRuns` depend on `[runs, branch]` or `[filteredRuns]`.

### httpx params dict pattern (backend)

**Source:** `mcp/src/services/github_client.py` lines 40–46
**Apply to:** `test_github_client.py` assertions — params are verified via `call_args.kwargs["params"]`

```python
# Backend pattern — params dict built conditionally (lines 40–44):
params: dict[str, str | int] = {"per_page": 30}
if branch:
    params["branch"] = branch
if status:
    params["status"] = status
# httpx call passes params= kwarg (line 46):
resp = await client.get(url, params=params)
```

### pytest AsyncMock + patch pattern (backend tests)

**Source:** `mcp/tests/test_github_client.py` lines 40–53
**Apply to:** `test_main.py` new stubs (patch at `src.api.artifacts.GitHubClient.list_workflow_runs`)

```python
@pytest.mark.asyncio
async def test_example(client):  # client fixture from conftest
    from unittest.mock import AsyncMock, patch
    with patch("src.api.artifacts.GitHubClient.list_workflow_runs",
               new_callable=AsyncMock, return_value=[...]) as mock_fn:
        response = await client.get("/github/runs")
    assert response.status_code == 200
    mock_fn.assert_called_once()
```

### Backend route default param fix

**Source:** `mcp/src/api/artifacts.py` lines 80–84
**The gap:** The FastAPI route has `status: str = "completed"` as query param default. This must change to `status: str = ""` so that requests without `?status=` return all runs.

```python
# BEFORE (artifacts.py line 83):
async def list_github_runs(
    branch: str = "",
    status: str = "completed",   # BUG: excludes in_progress runs
    github: GitHubClient = Depends(get_github_client),
) -> list[dict]:

# AFTER:
async def list_github_runs(
    branch: str = "",
    status: str = "",            # FIX: omit status → GitHub returns all statuses
    github: GitHubClient = Depends(get_github_client),
) -> list[dict]:
```

This is a backend fix that must be delivered alongside the `client.ts` change — both must land in the same plan (02-01) for PIPE-01 and PIPE-03 to work end-to-end.

---

## No Analog Found

All files in scope have direct analogs in the codebase (all are self-modifications to existing files). No greenfield files are required for Phase 02.

---

## Critical Implementation Order

Per RESEARCH.md §Summary: backend endpoint fix must precede frontend work because 02-02 and 02-03 depend on the corrected API shape.

1. **02-01** — Fix `client.ts` runs signature + fix `artifacts.py` `status` default + add `updated_at` to `types/index.ts` + add test stubs to both test files
2. **02-02** — Add branch filter, RunSummaryStrip, Vietnamese copy fix, KPI fontWeight fix to `Pipelines.tsx`
3. **02-03** — Add TrendCard + LiveIndicator to `Pipelines.tsx`

---

## Metadata

**Analog search scope:** `dashboard/src/`, `mcp/src/`, `mcp/tests/`
**Files scanned:** 8 source files read directly
**Pattern extraction date:** 2026-04-29

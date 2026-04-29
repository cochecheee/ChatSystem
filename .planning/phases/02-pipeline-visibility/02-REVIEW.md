---
phase: 02-pipeline-visibility
reviewed: 2026-04-29T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - mcp/src/api/artifacts.py
  - dashboard/src/api/client.ts
  - dashboard/src/types/index.ts
  - mcp/tests/test_main.py
  - mcp/tests/test_github_client.py
  - dashboard/src/pages/Pipelines.tsx
findings:
  critical: 3
  warning: 6
  info: 3
  total: 12
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-04-29T00:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Six files were reviewed covering the backend API layer (`artifacts.py`), the GitHub service client (`github_client.py` — read for cross-reference), the TypeScript API client and type definitions, and the React `Pipelines.tsx` page, plus two test modules.

The most serious defects are:

1. **The status-filter fix is incomplete.** `artifacts.py` calls `GitHubClient.list_workflow_runs` with `status=""`, which is the correct intent, but `github_client.py:38` declares the default parameter as `status="completed"`. Any call-site that omits the `status` argument (e.g., tool-invocation paths in the chat agent) will silently revert to `status=completed` and hide in-progress runs — the exact bug PIPE-03 was supposed to fix.

2. **Auth is silently disabled when `CI_API_KEY` is unset.** The `require_api_key` dependency returns `None` (allowing the request) whenever the env-var is absent. In a staging or misconfigured production deployment this permanently opens artifact processing to unauthenticated callers.

3. **`reprocessRun` is unauthenticated.** The endpoint `POST /github/runs/{run_id}/reprocess` carries neither `require_api_key` nor `_bearer` as a dependency, so any caller can wipe and re-trigger processing for any run.

4. **`client.ts` passes `undefined`-valued optional params to `URLSearchParams`**, which serializes them as the string `"undefined"`, corrupting GET requests.

5. **`renderRunRow` is re-created on every render** (defined inside the component body without `useCallback`), causing all visible run rows to re-render together with every state update.

---

## Critical Issues

### CR-01: `status="completed"` default in `GitHubClient` undoes the PIPE-03 fix

**File:** `mcp/src/services/github_client.py:38`
**Issue:** The method signature is `async def list_workflow_runs(self, workflow_name="", branch="", status="completed")`. The fix in `artifacts.py` explicitly passes `status=""`, but any other call-site that omits `status` — including the MCP chat-agent tool, any future caller — will silently revert to querying GitHub with `status=completed`, which excludes `in_progress` runs. The intent of the fix is therefore fragile and incomplete: the safe default should be `""` (no filter), not `"completed"`.

**Fix:**
```python
# github_client.py line 38
async def list_workflow_runs(
    self,
    workflow_name: str = "",
    branch: str = "",
    status: str = "",        # Changed: "" means no status filter (all runs)
) -> list[dict]:
```

---

### CR-02: Auth bypass when `CI_API_KEY` is not set — unauthenticated artifact processing

**File:** `mcp/src/api/artifacts.py:37-42`
**Issue:** `require_api_key` short-circuits with `return` (i.e., `None`, which FastAPI treats as success) when `settings.CI_API_KEY` is falsy. The docstring says "dev / test mode", but there is no guard preventing this state from reaching a staging or production deployment. An attacker (or misconfigured CI) can `POST /artifacts/process` without any credentials and trigger arbitrary artifact downloads and DB writes.

The same logic applies to the webhook endpoint (line 177): if `settings.CI_WEBHOOK_TOKEN` is empty, any unauthenticated POST is accepted. Both are consistent — but both share the same footgun.

**Fix:**
```python
async def require_api_key(api_key: str | None = Depends(_api_key_header)) -> None:
    expected = settings.CI_API_KEY
    if not expected:
        # Fail closed in non-testing environments
        import os
        if os.getenv("APP_ENV") != "testing":
            raise HTTPException(status_code=500, detail="CI_API_KEY is not configured")
        return  # allow only in explicit testing mode
    if api_key != expected:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
```

---

### CR-03: `POST /github/runs/{run_id}/reprocess` has no authentication

**File:** `mcp/src/api/artifacts.py:231-265`
**Issue:** The `reprocess_run` endpoint deletes all findings and artifacts for a given `run_id` and re-queues processing, but it has no `dependencies=[Depends(require_api_key)]` or bearer token check. Any unauthenticated client that can reach the MCP server can wipe and re-trigger processing for any run by ID. This is a data-loss and denial-of-service vector.

**Fix:**
```python
@router.post(
    "/github/runs/{run_id}/reprocess",
    status_code=202,
    dependencies=[Depends(require_api_key)],   # Add this line
)
async def reprocess_run(
    run_id: int,
    ...
```

---

## Warnings

### WR-01: `client.ts` — undefined optional params serialized as the string `"undefined"`

**File:** `dashboard/src/api/client.ts:21`
**Issue:** The `get<T>` helper iterates `params` with `url.searchParams.set(k, String(v))`. When a caller passes an object with `undefined` values — e.g., `api.findings.list({ project_id: undefined })` — `String(undefined)` produces `"undefined"`, so the server receives `?project_id=undefined` instead of no parameter at all. The cast on line 43 (`params as Record<string, string | number>`) strips TypeScript's awareness of optionality, making this silent.

**Fix:**
```typescript
// In get<T>, filter out undefined values before setting params:
if (params) {
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
  });
}
```

---

### WR-02: `refresh()` and `useEffect` duplicate the entire fetch logic — state inconsistency risk

**File:** `dashboard/src/pages/Pipelines.tsx:386-435`
**Issue:** The `refresh` callback (lines 386–407) and the `useEffect` body (lines 409–435) contain nearly identical fetch logic. The `refresh` callback calls `setRuns([])` and `setLoading(true)` before the fetch; the `useEffect` does not call `setRuns([])` on subsequent interval ticks (line 431), which is consistent. However, the main `useEffect` fetch path also does NOT call `setLoading(true)` (it starts with `loading=true` from `useState(true)` only on initial mount). If a future developer adds a second `useEffect` trigger (e.g., a dependency), the page will appear to load without showing the spinner.

The real defect is duplication: two copies of the auto-select logic (lines 395–400 and 417–422). Any fix to one is likely to miss the other.

**Fix:** Extract a shared `fetchRuns` function and call it from both `useEffect` and `refresh`:
```typescript
const fetchRuns = useCallback((showSpinner: boolean) => {
  if (showSpinner) { setLoading(true); setFetchError(null); setRuns([]); }
  api.github.runs()
    .then(arr => {
      setRuns(arr);
      setLoading(false);
      setSelectedId(prev => {
        if (prev != null && arr.some(r => r.id === prev)) return prev;
        const latestCi = arr.find(r => categorizeRun(r) === 'ci');
        const latestCd = arr.find(r => categorizeRun(r) === 'cd');
        return latestCi?.id ?? latestCd?.id ?? arr[0]?.id ?? null;
      });
    })
    .catch(e => { setFetchError(String(e)); setLoading(false); });
}, []);
```

---

### WR-03: `renderRunRow` defined inside component body — causes cascading re-renders

**File:** `dashboard/src/pages/Pipelines.tsx:481-520`
**Issue:** `renderRunRow` is a plain function defined in the component body on every render. Because it is not wrapped in `useCallback`, React cannot memoize the rows. Every state update (e.g., 30-second interval poll updating `runs`) causes all rendered rows to re-render regardless of whether their data changed. With many runs in the list, this degrades responsiveness. The function also closes over `selectedId` and `setSelectedId`, which means it captures a stale closure if either value changes between renders — though in this case the inline `onClick={() => setSelectedId(r.id)}` is fine, the closure capture of `selectedId` for the active-row comparison is correct.

The primary concern is that React best practice for inline renderers used in lists is to extract them into memoized child components or `useCallback`-wrapped functions so the virtual DOM diff remains efficient.

**Fix:** Extract into a `RunRow` component:
```tsx
const RunRow = React.memo(function RunRow({
  r, isLatest, isSelected, onSelect,
}: { r: WorkflowRun; isLatest: boolean; isSelected: boolean; onSelect: (id: number) => void }) {
  // ... row JSX, replace r.id === selectedId with isSelected
});
```

---

### WR-04: `SeverityBar` in the run-row always receives hardcoded zero counts

**File:** `dashboard/src/pages/Pipelines.tsx:507`
**Issue:** Line 507 renders `<SeverityBar counts={{ critical: 0, high: 0, medium: 0, low: 0 }} height={4} />` with all counts set to `0`. This is not a placeholder comment — it is rendered for the selected run row every time a run is selected. The bar will always be empty and mislead users into thinking there are no findings for a run, even when findings exist in the `RunPanel` below.

**Fix:** Either remove the `SeverityBar` from the run row entirely until finding counts per run are available in the runs list, or fetch and pass actual counts. A minimal fix is to remove the dead bar:
```tsx
// Remove lines 505-518 (the SeverityBar block inside renderRunRow)
// or add a TODO comment that this awaits per-run finding counts in the API response
```

---

### WR-05: `test_github_runs_all_statuses` mock patches the class method but the router uses a fresh instance

**File:** `mcp/tests/test_main.py:42-63`
**Issue:** The test patches `src.api.artifacts.GitHubClient.list_workflow_runs` as an `AsyncMock` on the class. This works because `get_github_client` creates a new instance per request and the patched class method is inherited. However, `mock_list.call_args` is checked **after** the `with patch(...)` block exits (line 49–50 fall inside the `with`, but line 56 accesses `mock_list.call_args` after). In Python, `mock_list` is still accessible after the context manager exits, so this is functional — but it is fragile: if the `with` block is refactored to also `assert_called_once()`, the assertion fires inside the scope where the mock is still active.

More critically, the test only asserts the `status` argument via positional or keyword introspection (lines 56–61), but it does not call `mock_list.assert_called_once()`. If the endpoint raises before calling `list_workflow_runs`, the test still passes because `response.status_code == 200` is checked before the mock call inspection — except that a 502 would fail the status assertion. This is acceptable, but the explicit `assert_called_once()` guard is missing.

**Fix:**
```python
mock_list.assert_called_once()  # Add after line 53 (assert len(data) == 2)
```

---

### WR-06: `test_branch_filter_param` does not verify client-side filtering vs. server-side filtering

**File:** `mcp/tests/test_github_client.py:156-177`
**Issue:** The test asserts that `branch="feature/x"` is forwarded as a query parameter to the GitHub API (correct behaviour). However, the mock returns two runs with different `head_branch` values (`feature/x` and `main`). The test then does not assert how many runs were returned to the caller — meaning if `list_workflow_runs` started doing client-side branch filtering *in addition to* the API param (double-filtering), or silently dropped the branch param and filtered locally, the test would still pass. The test should also assert that both runs are returned (since branch filtering is the API's job, not the client's).

**Fix:**
```python
# After mock_http.get.assert_called_once()
assert len(result) == 2, "Branch filtering is the API's job; client must return all runs from response"
```

---

## Info

### IN-01: `reprocess_run` imports `delete` from SQLAlchemy inside the function body

**File:** `mcp/src/api/artifacts.py:251`
**Issue:** `from sqlalchemy import delete` is imported inside the function at line 251, not at the module top level. This is not a bug but it is inconsistent with the rest of the file and makes the import invisible to static analysis and linting tools.

**Fix:** Move the import to the top of the file alongside the existing `from sqlalchemy import select`.

---

### IN-02: `WorkflowRun.updated_at` is optional in the TypeScript type but required for duration calculation

**File:** `dashboard/src/types/index.ts:38` / `dashboard/src/pages/Pipelines.tsx:19`
**Issue:** `WorkflowRun.updated_at` is typed as `string | undefined` (optional field with `?`). `formatDuration` guards with `if (!run.updated_at || !run.created_at) return '—'`, which is correct. However `run.created_at` is typed as non-optional `string`, yet `formatDuration` checks it defensively — this is fine but the guard is asymmetric. More importantly, if GitHub ever returns `updated_at: null` (as opposed to omitting it), the TypeScript type does not account for `null`, and `new Date(null).getTime()` returns `0`, producing a nonsensical negative duration.

**Fix:**
```typescript
updated_at?: string | null;   // Allow null explicitly
```
And in `formatDuration`:
```typescript
if (!run.updated_at || !run.created_at) return '—';
const ms = new Date(run.updated_at).getTime() - new Date(run.created_at).getTime();
if (ms < 0) return '—';   // Guard against clock skew / null edge cases
```

---

### IN-03: `console.error` left in production code paths

**File:** `dashboard/src/pages/Pipelines.tsx:403, 425`
**Issue:** Two `console.error('[Pipelines] fetch error:', e)` calls remain in production code. While debug logging is not a security risk here, it exposes internal error details (URL shapes, server error messages) in the browser console and should be removed or routed through a structured logging utility before shipping.

**Fix:** Remove both `console.error` calls, or replace with a project-level logger that strips output in production:
```typescript
// Replace:
console.error('[Pipelines] fetch error:', e);
// With: (if no logger exists, simply remove the line)
```

---

_Reviewed: 2026-04-29T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

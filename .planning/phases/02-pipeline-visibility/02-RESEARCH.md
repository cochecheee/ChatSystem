# Phase 02: Pipeline Visibility — Research

**Researched:** 2026-04-29
**Domain:** React frontend extension + FastAPI backend; GitHub Actions API integration
**Confidence:** HIGH (all findings verified directly from codebase)

---

## Summary

Phase 02 extends the existing `Pipelines.tsx` page and the backend `GET /github/runs` endpoint to deliver PIPE-01 through PIPE-05. The codebase is in an excellent starting position: the backend already accepts a `branch` filter param, the frontend already has 30-second polling, and the existing `AreaTrend`, `SeverityBar`, `SevBar` chart components are fully wired and ready to use with no new npm dependencies required.

The primary backend gap is that `GET /github/runs` currently hard-codes `status="completed"` from the frontend call in `client.ts` (`api.github.runs(status = 'completed')`), which excludes in-progress runs (PIPE-03). The backend route signature already accepts both `branch` and `status` params — only the frontend `client.ts` call site needs to be updated to pass `status=''` (or omit) so the GitHub API returns all runs regardless of completion status.

The primary frontend gaps are: (1) branch filter `<select>` UI with `useMemo`-derived `filteredRuns`, (2) `RunSummaryStrip` sub-render added to `renderRunRow`, (3) `TrendCard` inserted above `RunPanel` in the detail pane, and (4) `LiveIndicator` in the page header. All are isolated additions to the single `Pipelines.tsx` file per the UI-SPEC contract. No new files, no new npm packages.

**Primary recommendation:** The plan should treat this as three sequential deliverables — backend endpoint fix (02-01), frontend list + filter + summary strip (02-02), then trend chart + live indicator (02-03) — because 02-02 and 02-03 both depend on the corrected API shape from 02-01.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PIPE-01 | Pipeline page lists ALL GitHub workflow runs (not only SAST-tagged) | Backend `list_workflow_runs` already returns all runs; the frontend `status='completed'` filter is the only limiter — remove it |
| PIPE-02 | User can filter pipeline list by branch | Backend route already accepts `branch` param; frontend needs branch `<select>` + `useMemo(filteredRuns)` |
| PIPE-03 | In-progress runs show real-time status updates (auto-refresh without reload) | 30-second `setInterval` already exists in `Pipelines.tsx`; need to pass `status=''` to backend so in-progress runs are included |
| PIPE-04 | Trend chart — pass/fail/warning count over last 30 runs | `AreaTrend` component exists and is ready; trend data computed from `runs.slice(-30)` sorted chronologically |
| PIPE-05 | Each run row shows: tools executed, finding counts by severity, run duration | `SeverityBar` exists; tools come from artifacts already loaded in `RunPanel` — need a strategy for sidebar rows (see Tool Data Gap below) |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Fetch all workflow runs (PIPE-01) | API / Backend | — | `GitHubClient.list_workflow_runs` proxies GitHub API; frontend is a consumer |
| Branch filter state (PIPE-02) | Browser / Client | — | Pure UI state derived from already-fetched `runs` array — no separate API call needed |
| In-progress run inclusion (PIPE-03) | API / Backend | Browser / Client | Backend must pass `status=''` to GitHub; frontend already polls every 30s |
| Trend chart data (PIPE-04) | Browser / Client | — | Computed from `runs` array already in state; no backend endpoint needed |
| Run summary strip (PIPE-05) | Browser / Client | API / Backend | Tool tags need artifact data; findings-per-run already served by `/github/runs/{run_id}/findings` |
| Auto-refresh live indicator | Browser / Client | — | Derived from `runs.some(r => r.status === 'in_progress')` — pure client-side |

---

## Standard Stack

No new packages required for this phase. All chart and UI primitives already exist.

### Core (in use — verified)

| Library | Version | Purpose | Source |
|---------|---------|---------|--------|
| React | ^19.2.4 | UI framework | [VERIFIED: dashboard/package.json] |
| Vite | ^8.0.4 | Build tool | [VERIFIED: dashboard/package.json] |
| TypeScript | ~6.0.2 | Type safety | [VERIFIED: dashboard/package.json] |
| FastAPI | (in requirements.txt) | Backend API | [VERIFIED: mcp/src/main.py] |
| httpx | (in requirements.txt) | GitHub API HTTP client | [VERIFIED: mcp/src/services/github_client.py] |
| SQLAlchemy async | (in requirements.txt) | ORM + async sessions | [VERIFIED: mcp/src/models/entities.py] |

### Supporting (already in repo — no install needed)

| Component | File | What It Provides |
|-----------|------|------------------|
| `AreaTrend` | `dashboard/src/components/Charts.tsx` | Line+area chart with two series (primary = accent, secondary = dashed fg-4) |
| `SeverityBar` | `dashboard/src/components/Charts.tsx` | Proportional severity bar, height configurable |
| `AlertBanner` | `dashboard/src/components/AlertBanner.tsx` | Error/info banners (created in Phase 01) |
| `Badge` | `dashboard/src/components/Badge.tsx` | Status and severity chips (created in Phase 01) |
| `Icon` | `dashboard/src/components/Icon.tsx` | All needed icons: branch, clock, refresh, external, alert |

**Installation:** None required. All dependencies are already installed.

---

## Architecture Patterns

### System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  Browser (React, 30s poll)                                        │
│                                                                    │
│  [Branch <select>] → filteredRuns (useMemo)                       │
│       ↓                                                            │
│  [RunList: CI / CD sections]      [Detail pane]                   │
│  [RunSummaryStrip per row]  ←→    [TrendCard (AreaTrend)]         │
│       ↓ onClick                   [RunPanel → SeverityBoard etc]  │
│  selectedId state                                                  │
│                         ↑ setInterval 30s                         │
│                         |                                          │
│                  api.github.runs(branch?, status?)                │
│                         |                                          │
└─────────────────────────|────────────────────────────────────────┘
                          |
┌─────────────────────────|────────────────────────────────────────┐
│  FastAPI (mcp/src)       |                                         │
│                          ↓                                         │
│  GET /github/runs  →  GitHubClient.list_workflow_runs(           │
│                           workflow_name="",                        │
│                           branch=branch,                           │
│                           status=status  ← MUST BE "" not "completed" │
│                       )                                            │
│                          ↓                                         │
│              GitHub Actions REST API                               │
│    GET /repos/{owner}/{repo}/actions/runs?per_page=30&...         │
└──────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

No structural changes. All Phase 02 work is contained in:

```
mcp/src/
└── api/artifacts.py      # backend: /github/runs — already exists; status="" fix only

dashboard/src/
├── api/client.ts         # frontend: api.github.runs() — update default status param
├── pages/Pipelines.tsx   # all new sub-renders (RunSummaryStrip, TrendCard, LiveIndicator)
└── types/index.ts        # WorkflowRun: add updated_at field for duration calc (if missing)
```

### Pattern 1: Branch Filter with useMemo Derived List

**What:** A `<select>` bound to `branch` state; `filteredRuns` derived from `runs` via `useMemo` without a new API call.

**When to use:** Any filter that operates on data already in state — no server round-trip.

```tsx
// Source: UI-SPEC §Interaction Contract (verified against Pipelines.tsx existing patterns)
const [branch, setBranch] = useState<string>('all');

const filteredRuns = useMemo(() => {
  if (branch === 'all') return runs;
  return runs.filter(r => r.head_branch === branch);
}, [runs, branch]);

const branchOptions = useMemo(
  () => [...new Set(runs.map(r => r.head_branch))].sort(),
  [runs],
);
```

The `stats` KPI and trend chart always use `runs` (unfiltered). Only the sidebar list and run count sub-heading use `filteredRuns`.

### Pattern 2: AreaTrend Trend Data Shape

**What:** Transform the `runs` array into two parallel number arrays for `AreaTrend`.

```tsx
// Source: UI-SPEC §Implementation Notes #3; Charts.tsx interface (VERIFIED)
// AreaTrend props: values: number[], values2?: number[], height?: number

const trendData = useMemo(() => {
  const sorted = [...runs]
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    .slice(-30);
  return {
    failed: sorted.map(r => r.conclusion === 'failure' ? 1 : 0),
    passed: sorted.map(r => r.conclusion === 'success' ? 1 : 0),
  };
}, [runs]);

// Render:
// <AreaTrend values={trendData.failed} values2={trendData.passed} height={120} />
```

Note: `AreaTrend` renders hardcoded x-axis labels (`28d ago`, `21d`, `14d`, `7d`, `today`). These are cosmetic only — the actual data points are positionally mapped, so chronological ordering matters. [VERIFIED: Charts.tsx lines 16, 29–31]

### Pattern 3: Duration Computation

**What:** `WorkflowRun.updated_at` is not currently in the TypeScript type. It is available from the GitHub API response.

```tsx
// Source: UI-SPEC §Implementation Notes #4 (ASSUMED for updated_at presence in GitHub response)
// WorkflowRun type (VERIFIED: dashboard/src/types/index.ts) currently has:
//   created_at: string, head_sha: string — but NOT updated_at

// Required type addition:
interface WorkflowRun {
  // ...existing fields...
  updated_at?: string;   // ADD: from GitHub API, needed for duration display
}

function formatDuration(run: WorkflowRun): string {
  if (!run.updated_at || !run.created_at) return '—';
  const ms = new Date(run.updated_at).getTime() - new Date(run.created_at).getTime();
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  if (h > 0) return `${h}h ${m % 60}m`;
  return `${m}m ${s % 60}s`;
}
```

### Pattern 4: Tool Tags in Sidebar Row (PIPE-05 Critical Decision)

**What:** Tool tags in run rows require per-run artifact data. Artifacts are only loaded when `RunPanel` mounts for the selected run.

**The problem:** Loading artifacts for every run in the sidebar would require N additional API calls on page load, creating O(N) requests.

**Recommended approach** (matching UI-SPEC §Implementation Notes #5):
- Show `RunSummaryStrip` (tool tags + SeverityBar + counts) only for the **selected run's row** — mirror the `artifacts` state back up from `RunPanel` context.
- For non-selected rows: show only the existing 3 rows (status chip, run name, branch/time) — the strip is hidden as per the "no findings for run" state in the UI-SPEC.

**Alternative:** The backend could add a lightweight `/github/runs/{run_id}/summary` endpoint returning `{ tools: string[], counts: Record<string, number>, duration_ms: number }` per run, but this adds complexity and is not necessary for the MVP.

**Decision to lock in 02-01 plan:** Whether to (a) show strip only for selected run or (b) add a batch summary endpoint. The UI-SPEC explicitly says "If per-row tool data is not available without an extra API call per row, show tool tags only for the selected run's row." This is the safe default.

### Anti-Patterns to Avoid

- **Fetching artifacts per row on load:** Would create 30+ simultaneous GitHub API requests. `RunPanel` already fetches artifacts lazily on selection — reuse that data.
- **Polling with SSE/WebSocket:** The UI-SPEC explicitly mandates the existing 30-second `setInterval` — do not introduce SSE or WebSocket in Phase 02.
- **Rebuilding the run list state:** `runs` and `filteredRuns` are parallel; KPI stats and trend data must derive from `runs` (unfiltered), not `filteredRuns`.
- **Adding new CSS files or token variables:** The UI-SPEC prohibits adding new CSS variables or class names for concepts already covered in `tokens.css`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Severity bar in run row | Custom div with widths | `SeverityBar` from `Charts.tsx` | Already handles zero-total case with muted bar; has correct token colors |
| Line+area chart | Custom SVG | `AreaTrend` from `Charts.tsx` | Already has accent gradient fill, two-series support, dashed secondary line |
| Status badge coloring | Inline style map | `Badge` from `components/Badge.tsx` | Typed, covers all status and severity variants |
| Async loading/error state | Local try/catch boilerplate | `useAsyncAction` from `hooks/useAsyncAction.ts` | Created in Phase 01 specifically for this pattern |
| Tool tag display | Custom span | `.tool-tag` CSS class | Already defined in `tokens.css`, used throughout `Pipelines.tsx` for tool names |

---

## Key Findings: What Exists vs. What's Missing

### Backend (`mcp/src/api/artifacts.py`)

| Route | Status | Gap |
|-------|--------|-----|
| `GET /github/runs?branch=&status=` | EXISTS | Frontend call hardcodes `status='completed'` — excludes in-progress runs. Backend signature already correct. |
| `GET /github/runs/{run_id}/artifacts` | EXISTS | Fully functional — used by `RunPanel` |
| `GET /github/runs/{run_id}/findings` | EXISTS | Fully functional — used by `RunPanel` |
| `POST /github/runs/{run_id}/reprocess` | EXISTS | Fully functional |
| Run summary endpoint (tools+counts per run) | MISSING | Not needed if per-row strip is skipped for non-selected rows |

**Backend fix for PIPE-01 and PIPE-03:** In `dashboard/src/api/client.ts`, change:
```typescript
// BEFORE:
runs: (status = 'completed') =>
  get<WorkflowRun[]>('/github/runs', { status }),

// AFTER:
runs: (branch?: string) =>
  get<WorkflowRun[]>('/github/runs', branch ? { branch } : {}),
```
This removes the `status=completed` filter (returns all statuses including `in_progress`) and threads the optional branch param. The backend `github_client.py` already omits `status` from GitHub API params when the string is empty. [VERIFIED: github_client.py lines 40–47]

### Frontend (`dashboard/src/pages/Pipelines.tsx`)

| Feature | Status | What's Needed |
|---------|--------|---------------|
| Run list with CI/CD sections | EXISTS | Extend only |
| 30-second auto-refresh poll | EXISTS | Preserve as-is; update `runs()` call |
| KPI counters (Total/Passed/Failed/Running) | EXISTS | Preserve, ensure `stats` uses unfiltered `runs` |
| Branch filter `<select>` | MISSING | Add state + useMemo derivation |
| `LiveIndicator` pulsing dot | MISSING | Add inline to page header |
| `TrendCard` with `AreaTrend` | MISSING | Add to detail panel above RunPanel |
| `RunSummaryStrip` in run rows | MISSING | Add to `renderRunRow` for selected run only |
| Vietnamese copy strings | EXISTS (wrong) | Replace with English per UI-SPEC copywriting contract |
| `updated_at` on `WorkflowRun` type | MISSING | Add optional field to `types/index.ts` |

### GitHub API Data Shape

The `/github/runs` endpoint proxies the GitHub Actions API `GET /repos/{owner}/{repo}/actions/runs`. The response includes these fields relevant to Phase 02 (all already on the `WorkflowRun` TypeScript interface except `updated_at`): [VERIFIED: github_client.py; ASSUMED for exact GitHub API field names]

| Field | Type | Used For |
|-------|------|---------|
| `id` | number | Row key, selection ID |
| `name` | string | Workflow name display |
| `status` | string | `in_progress`, `queued`, `completed` |
| `conclusion` | string\|null | `success`, `failure`, `cancelled`, `skipped` |
| `created_at` | string (ISO) | `timeAgo()`, duration start |
| `updated_at` | string (ISO) | Duration end — **add to TypeScript type** |
| `head_branch` | string | Branch filter source |
| `head_sha` | string | SHA display in RunPanel |
| `run_number` | number | `#1234` display |
| `html_url` | string | GitHub link in RunPanel |

---

## Common Pitfalls

### Pitfall 1: `status='completed'` Excluding In-Progress Runs

**What goes wrong:** The current `api.github.runs()` call passes `status='completed'` to the backend, which forwards it to GitHub. In-progress runs return status `in_progress` from GitHub and are therefore excluded. The `LiveIndicator` will never appear and PIPE-03 is silently broken.

**Why it happens:** The initial client.ts signature defaulted to `completed` to reduce noise. This is acceptable for SAST processing but wrong for the pipeline visibility page.

**How to avoid:** Change `client.ts` to not pass a status filter, or pass `status=''`. The backend's `github_client.py` already handles the empty-string case correctly: it only adds `status` to params `if status:`. [VERIFIED: github_client.py line 41]

**Warning signs:** `LiveIndicator` never appears even when GitHub Actions shows runs in progress.

### Pitfall 2: Trend Chart `AreaTrend` Minimum Data Points

**What goes wrong:** `AreaTrend` computes `stepX = (w - padX * 2) / (values.length - 1)` — if `values.length === 1`, this is `Infinity` and the SVG path becomes invalid (NaN coordinates).

**Why it happens:** Division by `values.length - 1` when there is only one run.

**How to avoid:** The UI-SPEC already mandates showing `TrendCard` only when `runs.length >= 2`. Enforce this guard: `{filteredRuns.length >= 2 && <TrendCard runs={runs} />}`. Note: use unfiltered `runs` for trend data. [VERIFIED: Charts.tsx line 12]

### Pitfall 3: `filteredRuns` vs `runs` for Stats and Trend

**What goes wrong:** KPI counters and trend chart show data only for the filtered branch, making aggregate counts meaningless.

**Why it happens:** Using `filteredRuns` everywhere instead of selectively.

**How to avoid:** Stats (`total`, `passed`, `failed`, `running`) and trend data ALWAYS use `runs` (unfiltered). Only the sidebar run list and the sub-heading run count use `filteredRuns`. [VERIFIED: UI-SPEC §Implementation Notes #2]

### Pitfall 4: `SectionHeader` `position: sticky` Inside Filtered List

**What goes wrong:** CI/CD section headers are `position: sticky; top: 0` inside the scrollable sidebar. If `filteredRuns` results in zero items in one section, the empty state `.empty` div will overlap with the sticky header.

**Why it happens:** CSS sticky positioning interacts with empty content containers.

**How to avoid:** Keep the existing "No CI runs" / "No CD runs" `.empty` divs. The filtered empty state "No runs on {branch}" replaces the entire list pane content, not individual sections. [VERIFIED: Pipelines.tsx lines 523–530]

### Pitfall 5: Vietnamese Copy Strings

**What goes wrong:** The existing `Pipelines.tsx` has 4+ Vietnamese strings that will remain visible if not replaced.

**Strings to replace:** [VERIFIED: Pipelines.tsx lines 251, 256, 259, 299, 306–308, 543–544]

| Line | Current (Vietnamese) | Replace With |
|------|---------------------|-------------|
| 251 | `Xoá findings cũ và xử lý lại run #...` | `Delete old findings and reprocess run #${run.run_number}?` |
| 256 | `Đang xử lý ${res.deleted_artifacts} artifact cũ...` | `Reprocessing ${res.deleted_artifacts} artifacts — results will update in ~10s…` |
| 259 | `Lỗi: ${e}` | `Reprocess failed: ${e}` |
| 282 | `Đang xử lý…` | `Reprocessing…` |
| 299 | `Đang tải kết quả scan…` | `Loading scan results…` |
| 306–308 | Vietnamese findings empty state | `No findings for this run.\nArtifacts may have expired (retention: 1 day) or CI has not triggered a webhook.` |
| 543–544 | `Đang tải…` / `Chọn một pipeline run...` | `Loading…` / `Select a pipeline run to view results` |

### Pitfall 6: `fontWeight: 700` in Existing KPI Cards

**What goes wrong:** The UI-SPEC prohibits fontWeight 500 and 700 — only 400 and 600 are permitted. The existing KPI cards use `fontWeight: 700`.

**Why it happens:** The KPI cards were written before the Phase 02 typography contract.

**How to avoid:** The UI-SPEC §Implementation Notes #10 explicitly preserves `fontSize: 18` but does not grant an exception for `fontWeight: 700`. The KPI counter weight should be corrected to `600` during Phase 02 work. **Clarification:** The UI-SPEC says correct any 500/700 weights encountered — so fix these during implementation. [VERIFIED: Pipelines.tsx lines 489, 492, 495, 499]

---

## Code Examples

### AreaTrend Usage (verified interface)

```tsx
// Source: dashboard/src/components/Charts.tsx lines 1-35 (VERIFIED)
// Interface: values: number[], values2?: number[], height?: number

// Correct usage for PIPE-04:
<AreaTrend
  values={trendData.failed}    // primary series: accent color, area fill
  values2={trendData.passed}   // secondary: dashed, var(--fg-4)
  height={120}                 // compact override of default 200
/>
```

### SeverityBar Usage (verified interface)

```tsx
// Source: dashboard/src/components/Charts.tsx lines 49-61 (VERIFIED)
// Interface: counts: Record<string, number>, height?: number

// Correct usage for PIPE-05 run row strip:
const counts = { critical: 2, high: 5, medium: 12, low: 3 };
<SeverityBar counts={counts} height={4} />
// Zero-total case: renders a muted bar automatically (lines 51-52)
```

### Backend: api.github.runs() updated signature

```typescript
// Source: dashboard/src/api/client.ts lines 52-54 (VERIFIED — current)
// CURRENT (broken for PIPE-01 and PIPE-03):
runs: (status = 'completed') =>
  get<WorkflowRun[]>('/github/runs', { status }),

// REQUIRED change:
runs: (branch?: string) =>
  get<WorkflowRun[]>('/github/runs', branch ? { branch } : {}),
```

### LiveIndicator (inline in Pipelines.tsx)

```tsx
// Source: UI-SPEC §Layout Contract — Auto-refresh indicator (VERIFIED pattern)
// All tokens verified against tokens.css

const hasInProgress = runs.some(r => r.status === 'in_progress');

// In page header JSX, adjacent to Refresh Runs button:
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

### TrendCard (inline in Pipelines.tsx)

```tsx
// Source: UI-SPEC §Layout Contract — Trend chart placement (VERIFIED)
// Only render when runs.length >= 2 (guard against AreaTrend division by zero)
{runs.length >= 2 && (
  <div className="card" style={{ marginBottom: 14 }}>
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
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `status='completed'` filter in runs fetch | Remove status filter (all runs) | Phase 02 | Enables in-progress run display |
| No branch filter | Client-side `useMemo` filter on `head_branch` | Phase 02 | No additional API call needed |
| Vietnamese copy strings in Pipelines.tsx | English copy per UI-SPEC | Phase 02 | Consistency requirement |

**Deprecated/outdated:**
- `api.github.runs(status = 'completed')` signature: replace with `api.github.runs(branch?)` in Phase 02.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | GitHub API returns `updated_at` on workflow run objects | Code Examples / Duration Computation | Duration display shows `—` for all runs; low UI risk |
| A2 | `runs.sort` by `created_at` ascending produces correct chronological order for trend chart | Pattern 2 | Trend chart x-axis ordering could be reversed; the data is still correct |

---

## Open Questions

1. **Tool tags for non-selected run rows**
   - What we know: Loading artifacts per row is O(N) API calls; the UI-SPEC recommends showing tags only for the selected run.
   - What's unclear: Should 02-01 add a `/github/runs/batch-summary` endpoint, or should 02-02 simply show tags only for the selected run?
   - Recommendation: Plan 02-02 should show tags only for the selected run (matching RunPanel artifact state). Add a note in 02-01 that a batch summary endpoint can be added in a future phase if needed.

2. **`WorkflowRun.updated_at` field availability**
   - What we know: The TypeScript type lacks `updated_at`; the GitHub API does return it.
   - What's unclear: Whether the backend proxy currently strips unknown fields or passes them through as `list[dict]`.
   - Recommendation: The backend returns `list[dict]` (not a typed Pydantic model) for `/github/runs` — all fields pass through. Frontend should add `updated_at?: string` to the `WorkflowRun` type. [VERIFIED: artifacts.py line 80 — return type is `list[dict]`]

---

## Environment Availability

Step 2.6: Environment is code/config-only changes (React + FastAPI). No new external tools, CLIs, or services introduced.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js / npm | Frontend build | Assumed available (node_modules present) | — | — |
| Python / uvicorn | Backend | Assumed available (.venv present in mcp/) | — | — |
| GitHub Token | `/github/runs` API | Must be set in `.env` | — | Page shows "No runs — check GITHUB_TOKEN" |

---

## Validation Architecture

`workflow.nyquist_validation: true` in config.json — this section is required.

### Test Framework

| Property | Value |
|----------|-------|
| Framework (backend) | pytest + pytest-asyncio (`mcp/pytest.ini`: `asyncio_mode = auto`) |
| Framework (frontend) | Playwright (`dashboard/playwright.config.ts`) |
| Config file (backend) | `mcp/pytest.ini` |
| Config file (frontend) | `dashboard/playwright.config.ts` |
| Quick run (backend) | `cd mcp && python -m pytest tests/test_main.py -x -q` |
| Full suite (backend) | `cd mcp && python -m pytest -x -q` |
| E2E (frontend) | `cd dashboard && npm run test:e2e` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PIPE-01 | `/github/runs` returns all statuses (not only completed) | unit (backend) | `pytest tests/test_main.py -k "test_github_runs" -x` | ❌ Wave 0 |
| PIPE-02 | Branch filter param threads to GitHub client | unit (backend) | `pytest tests/test_github_client.py -k "test_branch_filter" -x` | ❌ Wave 0 |
| PIPE-03 | In-progress runs included in list response | unit (backend) | same as PIPE-01 test | ❌ Wave 0 |
| PIPE-04 | Trend chart renders with >= 2 runs | E2E / manual | Playwright — verify TrendCard visible | ❌ Wave 0 |
| PIPE-05 | Run summary strip shows tools + severity bar | E2E / manual | Playwright — verify RunSummaryStrip on selected row | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd mcp && python -m pytest tests/test_main.py tests/test_github_client.py -x -q`
- **Per wave merge:** `cd mcp && python -m pytest -x -q`
- **Phase gate:** Full backend suite green + manual Playwright smoke before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `mcp/tests/test_main.py::test_github_runs_all_statuses` — covers PIPE-01/PIPE-03
- [ ] `mcp/tests/test_github_client.py::test_branch_filter_param` — covers PIPE-02 backend
- [ ] Frontend: Playwright smoke for Pipelines page is a manual-only check (no existing `tests/e2e/` directory in dashboard) — acceptable for Phase 02

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Existing JWT auth unchanged |
| V3 Session Management | no | Unchanged |
| V4 Access Control | no | No new protected routes |
| V5 Input Validation | yes | `branch` query param passed to GitHub API — must be validated/sanitized |
| V6 Cryptography | no | Not applicable |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| `branch` param injection into GitHub API URL | Tampering | `httpx` passes params as URL-encoded query string via `params` dict — not string interpolation; injection risk is LOW [VERIFIED: github_client.py lines 44-46] |
| Exposing all GitHub workflow run metadata to unauthenticated callers | Information Disclosure | The existing `/github/runs` route has no auth dependency. This is pre-existing — Phase 02 does not worsen the posture. Auth is handled by the CI_API_KEY middleware only on processing endpoints. |
| XSS via run names rendered in UI | XSS | React JSX escapes string content automatically — no `dangerouslySetInnerHTML` is used in Pipelines.tsx |

**Branch param note:** The `branch` value from the frontend `<select>` is populated from `runs.map(r => r.head_branch)` — data that has already been received from GitHub. The value is sent back to the backend as a URL query parameter and forwarded to GitHub API via httpx params dict. No SQL queries or template strings involved. [VERIFIED: github_client.py, artifacts.py]

---

## Sources

### Primary (HIGH confidence — verified from codebase)

- `dashboard/src/pages/Pipelines.tsx` — complete current implementation reviewed
- `dashboard/src/components/Charts.tsx` — AreaTrend, SeverityBar, Sparkline interfaces verified
- `dashboard/src/api/client.ts` — existing `api.github.runs(status)` signature verified
- `dashboard/src/types/index.ts` — WorkflowRun type fields verified; `updated_at` confirmed absent
- `mcp/src/api/artifacts.py` — all backend routes verified; `GET /github/runs` signature confirmed
- `mcp/src/services/github_client.py` — `list_workflow_runs` param handling verified
- `mcp/src/models/entities.py` — Artifact.github_run_id relationship verified
- `.planning/phases/02-pipeline-visibility/02-UI-SPEC.md` — locked design contract read in full
- `.planning/phases/01-ui-ux-overhaul/01-01-SUMMARY.md` and `01-02-SUMMARY.md` — Phase 01 deliverables confirmed
- `.planning/phases/01-ui-ux-overhaul/01-PATTERNS.md` — Phase 01 patterns read
- `dashboard/playwright.config.ts` and `mcp/pytest.ini` — test infrastructure confirmed

### Secondary (MEDIUM confidence)

- GitHub Actions REST API field names (including `updated_at`) — [ASSUMED: standard GitHub API contract, not verified via live API call in this session]

---

## Metadata

**Confidence breakdown:**

- Backend gap identification: HIGH — code read directly, routes and params verified
- Frontend extension patterns: HIGH — all component interfaces read from source files
- AreaTrend data shape: HIGH — interface and rendering logic read from Charts.tsx
- `updated_at` field presence from GitHub API: LOW — not verified via live API call; marked as ASSUMED
- Security assessment: HIGH — code paths traced to verify no new attack surface

**Research date:** 2026-04-29
**Valid until:** 2026-05-29 (stable codebase; low churn risk)

---
phase: 02-pipeline-visibility
verified: 2026-04-29T06:00:00Z
status: gaps_found
score: 4/5 must-haves verified
overrides_applied: 0
gaps:
  - truth: "Each run row shows tool summary and finding counts"
    status: partial
    reason: "RunSummaryStrip is present and shows duration, but SeverityBar counts are hardcoded zeros (not real finding counts) and no tool names are displayed. PIPE-05 requires 'finding counts by severity' — hardcoded zeros do not satisfy this."
    artifacts:
      - path: "dashboard/src/pages/Pipelines.tsx"
        issue: "SeverityBar at line 507 renders { critical: 0, high: 0, medium: 0, low: 0 } — static stub, not real per-run finding counts. No tool names rendered in the strip."
    missing:
      - "Replace hardcoded zero counts in RunSummaryStrip with real per-run finding counts fetched from /github/runs/{run_id}/findings or passed down from RunPanel state"
      - "Add tool name tags to RunSummaryStrip (requires artifact list or findings grouping by tool)"
---

# Phase 2: Pipeline Visibility Verification Report

**Phase Goal:** Pipeline page shows all GitHub workflow runs with real-time status, branch filtering, trend charts, and per-run summaries
**Verified:** 2026-04-29T06:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | All runs from GitHub Actions appear in pipeline list (not only SAST-tagged) — PIPE-01 | VERIFIED | `artifacts.py` line 82: `status: str = ""` — empty default means no status filter forwarded to GitHub API. `client.ts` line 53-54: `runs: (branch?: string)` — no `status` param in request. `github_client.py` `if status:` guard skips adding empty string to params. Test `test_github_runs_all_statuses` regression-guards this. |
| 2 | Branch filter narrows list correctly — PIPE-02 | VERIFIED | `filteredRuns` useMemo at Pipelines.tsx lines 451-454 filters `runs` by `branch` state. `ciRuns`/`cdRuns` derive from `filteredRuns` (line 457-464). Branch `<select>` with "All branches" default at lines 538-547. Sub-heading shows `"N of M runs"` when filtered. |
| 3 | In-progress run status updates without manual reload — PIPE-03 | VERIFIED | 30-second `setInterval` at Pipelines.tsx line 429 calls `api.github.runs()` with no status filter — returns in_progress runs. `hasInProgress` derived from unfiltered `runs` at line 478. `LiveIndicator` pulsing dot + "Live" label renders when `hasInProgress` is true (lines 553-566). |
| 4 | Trend chart visible with at least 2 data points — PIPE-04 | VERIFIED | `trendData` useMemo at lines 467-475 computes from unfiltered `runs`, sorted ascending by `created_at`, sliced to last 30. TrendCard with `<AreaTrend values={trendData.failed} values2={trendData.passed} height={120} />` guarded by `runs.length >= 2` at lines 625-637. Guard prevents SVG division-by-zero for single-run case. |
| 5 | Each run row shows tool summary and finding counts — PIPE-05 | PARTIAL / FAILED | `RunSummaryStrip` structure is present behind `r.id === selectedId` guard (lines 504-518): divider + SeverityBar + clock icon + `formatDuration`. HOWEVER: `SeverityBar` is called with `{ critical: 0, high: 0, medium: 0, low: 0 }` — hardcoded zeros, not real finding counts. No tool names displayed. SUMMARY.md documents this as a "known stub." The duration display is real (uses `updated_at - created_at`), but severity counts do not reflect actual findings. |

**Score:** 4/5 truths verified

### Deferred Items

None.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `mcp/src/api/artifacts.py` | GET /github/runs with `status: str = ""` default | VERIFIED | Line 82: `status: str = ""` confirmed. No `status=completed` anywhere in file. |
| `dashboard/src/api/client.ts` | `runs: (branch?: string)` — no hardcoded status | VERIFIED | Line 53-54: `runs: (branch?: string) => get<WorkflowRun[]>('/github/runs', branch ? { branch } : {})` |
| `dashboard/src/types/index.ts` | WorkflowRun interface with `updated_at?: string` | VERIFIED | Line 38: `updated_at?: string;` present after `created_at` |
| `mcp/tests/test_main.py` | `test_github_runs_all_statuses` test function | VERIFIED | Lines 24-63: full test function present, patches `GitHubClient.list_workflow_runs`, asserts `in_progress` status returned, asserts `status=""` passed |
| `mcp/tests/test_github_client.py` | `test_branch_filter_param` and `test_no_status_param_when_empty` | VERIFIED | Lines 156-177 and 181-192: both test functions present with correct assertions |
| `dashboard/src/pages/Pipelines.tsx` | Branch filter, filteredRuns, trendData, hasInProgress, LiveIndicator, TrendCard, RunSummaryStrip | PARTIAL | All features present. filteredRuns (5 occurrences), setBranch (line 543), All branches (line 545), formatDuration (lines 18-26, 514), Pipeline Trend (line 628), hasInProgress (lines 478, 553), LiveIndicator (lines 553-566), trendData (lines 467-475, 634), runs.length >= 2 guard (line 625). SeverityBar rendered with hardcoded zeros (line 507). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `dashboard/src/api/client.ts` | `mcp/src/api/artifacts.py` | GET /github/runs — branch forwarded, status omitted | WIRED | `runs: (branch?: string) => get('/github/runs', branch ? { branch } : {})` sends branch if truthy, no status. Backend `status: str = ""` default ensures all runs returned. |
| `mcp/src/api/artifacts.py` | `mcp/src/services/github_client.py` | `status=""` causes github_client to skip status in GitHub API params | WIRED | `github_client.py`: `if status: params["status"] = status` — empty string is falsy, param not added. Confirmed by `test_no_status_param_when_empty`. |
| `branch state` | `filteredRuns` useMemo | `runs.filter(r => r.head_branch === branch)` | WIRED | Pipelines.tsx line 451-454: `filteredRuns = useMemo(() => { if (branch === 'all') return runs; return runs.filter(r => r.head_branch === branch); }, [runs, branch])` |
| `filteredRuns` | `ciRuns/cdRuns` split | `categorizeRun()` iterates `filteredRuns` | WIRED | Pipelines.tsx lines 457-464: `for (const r of filteredRuns)` confirmed |
| `runs (unfiltered)` | `stats` memo | KPI totals always reflect all runs | WIRED | Pipelines.tsx line 439-444: `stats = useMemo(() => ({ total: runs.length, ... }), [runs])` — depends on unfiltered `runs` |
| `runs (unfiltered)` | `trendData` useMemo | sorted by `created_at` ascending, sliced to last 30 | WIRED | Pipelines.tsx lines 467-475: `[...runs].sort(...).slice(-30)` with `[runs]` dependency |
| `trendData` | `AreaTrend` component | `values={trendData.failed}` `values2={trendData.passed}` `height={120}` | WIRED | Pipelines.tsx line 634: `<AreaTrend values={trendData.failed} values2={trendData.passed} height={120} />` |
| `runs (unfiltered)` | `hasInProgress` | `runs.some(r => r.status === 'in_progress')` | WIRED | Pipelines.tsx line 478: `const hasInProgress = runs.some(r => r.status === 'in_progress')` |
| `RunSummaryStrip SeverityBar` | real finding counts | per-run findings from API | NOT WIRED | `SeverityBar` at line 507 uses `{ critical: 0, high: 0, medium: 0, low: 0 }` — disconnected from findings state. Real counts are loaded in `RunPanel` (separate component) but not passed into the row renderer. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `Pipelines.tsx` KPI stats | `stats.total/passed/failed/running` | `runs` state from `api.github.runs()` | Yes — computed from live fetch | FLOWING |
| `Pipelines.tsx` filteredRuns | `filteredRuns` | `runs` filtered by `branch` state | Yes — client-side filter of live data | FLOWING |
| `Pipelines.tsx` trendData | `trendData.failed` / `trendData.passed` | `runs` sorted/sliced | Yes — computed from live run data | FLOWING |
| `Pipelines.tsx` hasInProgress | `hasInProgress` | `runs.some(r => r.status === 'in_progress')` | Yes — computed from live run status | FLOWING |
| `Pipelines.tsx` RunSummaryStrip duration | `formatDuration(r)` | `r.updated_at - r.created_at` from WorkflowRun | Yes — real if `updated_at` present in API response | FLOWING |
| `Pipelines.tsx` RunSummaryStrip SeverityBar | `{ critical: 0, high: 0, medium: 0, low: 0 }` | Hardcoded literal | No — always zero, not fetched | HOLLOW_PROP |

### Behavioral Spot-Checks

Step 7b: SKIPPED — the project requires a running dev server and live GitHub API token to validate real-time behavior. Spot-checks not feasible without these services.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PIPE-01 | 02-01-PLAN.md | All GitHub workflow runs visible (not only SAST-tagged) | SATISFIED | `status: str = ""` in artifacts.py; `runs: (branch?)` in client.ts; `test_github_runs_all_statuses` passes |
| PIPE-02 | 02-01-PLAN.md, 02-02-PLAN.md | Branch filter narrows pipeline list | SATISFIED | `filteredRuns` useMemo, branch `<select>`, `ciRuns`/`cdRuns` from `filteredRuns`, `test_branch_filter_param` passes |
| PIPE-03 | 02-01-PLAN.md, 02-03-PLAN.md | In-progress runs update without manual reload | SATISFIED | 30s `setInterval` with no-status API call; `hasInProgress` + LiveIndicator; `test_github_runs_all_statuses` asserts `in_progress` included |
| PIPE-04 | 02-03-PLAN.md | Trend chart with pass/fail over last 30 runs | SATISFIED | `trendData` useMemo, TrendCard with `AreaTrend`, `runs.length >= 2` guard |
| PIPE-05 | 02-02-PLAN.md | Run row shows tool summary and finding counts | BLOCKED | RunSummaryStrip structure present with duration, but SeverityBar counts are hardcoded zeros — no real finding counts. No tool names rendered. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `dashboard/src/pages/Pipelines.tsx` | 507 | `SeverityBar counts={{ critical: 0, high: 0, medium: 0, low: 0 }}` — hardcoded zeros passed to rendered component | WARNING | SeverityBar always shows a muted (zero-count) bar regardless of actual findings for the run. The `RunPanel` component fetches real findings via `api.github.runFindings(run.id)` but that data is not accessible to the `renderRunRow` closure. PIPE-05 partially blocked. |
| `mcp/src/api/artifacts.py` | 260 | Vietnamese string `"Không tìm thấy project gắn với run này."` in error response | INFO | Not a blocker; only in the reprocess route error path. Phase 02 clean-up scope was Pipelines.tsx only. |

### Gaps Summary

One gap blocks full PIPE-05 satisfaction.

**PIPE-05 — Hardcoded zero severity counts in RunSummaryStrip.**

The `RunSummaryStrip` sub-render inside `renderRunRow` uses `SeverityBar` with static `{ critical: 0, high: 0, medium: 0, low: 0 }`. This means the strip always shows a muted bar with no actual finding counts, regardless of how many findings a run has. The requirement states "finding counts by severity" — this is not met.

The duration display (`formatDuration`) is correctly wired and real. The strip's structural presence is also real. What's missing is the data connection from findings to the row renderer.

Root cause: `renderRunRow` only receives the `WorkflowRun` object. Findings are loaded asynchronously inside `RunPanel` (a separate component with its own state). To fix this, the phase needs either: (a) a per-run finding count cache derived from `api.github.runFindings()` calls, or (b) findings counts pre-fetched alongside runs and stored in the page-level state.

The plan's own SUMMARY.md explicitly documents this as a "known stub" — the decision was to defer real counts to a future plan. However, PIPE-05 as written in REQUIREMENTS.md requires "finding counts by severity" and the current implementation does not deliver this.

---

_Verified: 2026-04-29T06:00:00Z_
_Verifier: Claude (gsd-verifier)_

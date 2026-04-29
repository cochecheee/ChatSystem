---
phase: 02-pipeline-visibility
plan: "03"
subsystem: dashboard-frontend
tags: [react, charts, trend, live-indicator, pipeline-visibility]
dependency_graph:
  requires:
    - 02-01 (WorkflowRun type with status field, api.github.runs() no-arg signature)
    - 02-02 (Pipelines.tsx structure with branch filter, CI/CD sections, filteredRuns useMemo)
  provides:
    - trendData useMemo (pass/fail history from unfiltered runs, last 30, chronological)
    - TrendCard component (AreaTrend chart in detail panel, guarded by runs.length >= 2)
    - hasInProgress boolean (live detection from unfiltered runs)
    - LiveIndicator (pulsing accent dot + "Live" label in page header)
  affects:
    - dashboard/src/pages/Pipelines.tsx
tech_stack:
  added: []
  patterns:
    - useMemo for trendData derived from unfiltered runs (not filteredRuns)
    - DoS guard: runs.length >= 2 prevents AreaTrend SVG division-by-zero
    - Inline derived boolean (hasInProgress) rather than useMemo for simple synchronous derivation
    - CSS animation reuse: pulse keyframe from tokens.css
key_files:
  created: []
  modified:
    - dashboard/src/pages/Pipelines.tsx
decisions:
  - trendData derives from unfiltered `runs` array (not filteredRuns) so trend reflects all-branch history, not the filtered view
  - hasInProgress is a plain boolean derivation (not useMemo) because it is synchronous and has no performance concern
  - TrendCard guard uses `runs.length >= 2` (unfiltered) to match trendData's data source and prevent AreaTrend division-by-zero (T-02-08 mitigated)
  - LiveIndicator uses the existing `pulse` keyframe defined in tokens.css rather than adding new CSS
metrics:
  duration: "~8 minutes"
  completed: "2026-04-29T05:11:56Z"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 1
---

# Phase 02 Plan 03: TrendCard and LiveIndicator Summary

AreaTrend pass/fail chart in detail panel and pulsing LiveIndicator in page header added to Pipelines.tsx, completing PIPE-03 and PIPE-04 frontend visibility requirements.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add trendData useMemo and TrendCard in detail panel | 7aaf7c6 | dashboard/src/pages/Pipelines.tsx |
| 2 | Add hasInProgress and LiveIndicator in page header | 7aaf7c6 | dashboard/src/pages/Pipelines.tsx |

Note: Both tasks were implemented in a single atomic commit since no checkpoint separated them and there was no intermediate compilable state required.

## What Was Built

### Task 1: trendData useMemo + TrendCard
- Added `AreaTrend` to the Charts import alongside `SeverityBar`
- Added `trendData` useMemo after the `ciRuns/cdRuns` useMemo, computing from unfiltered `runs`:
  - Sorts runs by `created_at` ascending
  - Slices the last 30 runs
  - Maps `failed` series: 1 if `conclusion === 'failure'`, else 0
  - Maps `passed` series: 1 if `conclusion === 'success'`, else 0
- Added TrendCard JSX above RunPanel in the detail panel:
  - Guarded by `{runs.length >= 2 && ...}` to prevent AreaTrend SVG stepX division-by-zero
  - Card header: "Pipeline Trend" + muted subtitle "Pass / fail over last 30 runs"
  - Body: `<AreaTrend values={trendData.failed} values2={trendData.passed} height={120} />`

### Task 2: hasInProgress + LiveIndicator
- Added `hasInProgress = runs.some(r => r.status === 'in_progress')` after trendData useMemo
- Added LiveIndicator JSX adjacent to the Refresh button in page header:
  - 6px accent-colored circle with `animation: 'pulse 1.5s ease-in-out infinite'`
  - "Live" label in `var(--ts-xs)` size, weight 600, `var(--fg-3)` color
  - Guarded by `{hasInProgress && ...}`
- Confirmed 30-second setInterval polling is unchanged (still calls `api.github.runs()` with no args)

## Verification Results

- `npx tsc --noEmit`: exits 0 (zero TypeScript errors)
- `python -m pytest tests/test_main.py tests/test_github_client.py -x -q`: 13 passed in 0.28s
- All acceptance criteria grep checks pass

## Deviations from Plan

None — plan executed exactly as written.

Tasks 1 and 2 were committed in a single commit (7aaf7c6) because both edits were applied to the same file before staging, and there was no TypeScript intermediate compilation step that would require separating them. All semantic requirements of both tasks are present in the commit.

## Threat Model Coverage

| Threat ID | Status |
|-----------|--------|
| T-02-07 (Information Disclosure - TrendCard history) | Accepted as planned — trend is a computed summary of already-visible data |
| T-02-08 (DoS - AreaTrend division-by-zero) | Mitigated — `runs.length >= 2` guard implemented |
| T-02-09 (XSS - TrendCard strings) | Accepted as planned — hardcoded string literals only |

## Known Stubs

None. All data flows are wired: trendData derives from live `runs` state, hasInProgress derives from live `runs` state.

## Self-Check: PASSED

- [x] `dashboard/src/pages/Pipelines.tsx` exists and contains all required additions
- [x] Commit 7aaf7c6 exists in worktree git log
- [x] `AreaTrend` imported at line 3
- [x] `trendData` useMemo defined at line 467
- [x] `Pipeline Trend` heading at line 628
- [x] `runs.length >= 2` guard at line 625
- [x] `hasInProgress` defined at line 478, used at line 553
- [x] `animation: 'pulse 1.5s ease-in-out infinite'` at line 560
- [x] `setInterval` still present at line 429 (unchanged)
- [x] TypeScript: zero errors
- [x] Backend pytest: 13 passed

---
phase: 02-pipeline-visibility
plan: "02"
subsystem: dashboard/frontend
tags: [branch-filter, run-summary-strip, i18n, kpi, pipelines]
dependency_graph:
  requires: ["02-01"]
  provides: ["PIPE-02", "PIPE-05"]
  affects: ["dashboard/src/pages/Pipelines.tsx"]
tech_stack:
  added: []
  patterns: ["useMemo derived state", "client-side array filtering", "conditional row sub-component"]
key_files:
  modified:
    - dashboard/src/pages/Pipelines.tsx
decisions:
  - "filteredRuns derived via useMemo from runs + branch state; stats memo kept on unfiltered runs per spec"
  - "KPI fontWeight corrected from 700 to 600 (all 4 cards) per design tokens rule"
  - "RunSummaryStrip rendered inline inside renderRunRow behind r.id === selectedId guard"
  - "Branch filter placed adjacent to Refresh button in header flex row for visual grouping"
metrics:
  duration: "~12 minutes"
  completed: "2026-04-29"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 02 Plan 02: Branch Filter, RunSummaryStrip, English Copy Summary

Branch filter with `filteredRuns` useMemo (PIPE-02), RunSummaryStrip with SeverityBar + duration (PIPE-05), 8 Vietnamese-to-English copy replacements, and 4 KPI fontWeight corrections — all in a single Pipelines.tsx edit with zero new CSS or API calls.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add branch filter state, derived lists, and RunSummaryStrip | 817ac48 | dashboard/src/pages/Pipelines.tsx |
| 2 | Replace Vietnamese copy strings with English equivalents | 5ba60b3 | dashboard/src/pages/Pipelines.tsx |

## What Was Built

**Task 1 — Branch filter, filteredRuns, RunSummaryStrip, KPI fix:**
- `SeverityBar` imported from `../components/Charts`
- `formatDuration(run)` helper added (returns formatted `Xh Ym` / `Mm Ss` string using `updated_at - created_at`)
- `branch` state (`useState<string>('all')`) added after existing state declarations
- `branchOptions` useMemo: unique sorted branch names from unfiltered `runs`
- `filteredRuns` useMemo: filters `runs` by `branch`; returns all when `branch === 'all'`
- `ciRuns`/`cdRuns` useMemo redirected to iterate `filteredRuns` (not `runs`)
- `stats` useMemo kept on unfiltered `runs` (KPI totals always reflect all runs)
- Branch filter `<select>` added in page header with Icon prefix and "All branches" default option
- Sub-heading updated: shows `"N of M runs"` when branch filtered, `"M recent runs"` otherwise
- 4 KPI counter `fontWeight: 700` → `fontWeight: 600` (Total, Passed, Failed, Running)
- RunSummaryStrip appended to renderRunRow behind `r.id === selectedId` guard: divider + `SeverityBar` (height=4, zero counts) + clock icon + `formatDuration` result

**Task 2 — English copy replacements (8 strings):**
- Confirm dialog: `Xoá findings cũ và xử lý lại run #...` → `Delete old findings and reprocess run #...`
- Success message: `Đang xử lý N artifact cũ — kết quả sẽ cập nhật...` → `Reprocessing N artifacts — results will update in ~10s…`
- Error message: `` `Lỗi: ${e}` `` → `` `Reprocess failed: ${e}` ``
- Button label: `Đang xử lý…` → `Reprocessing…`
- Loading state: `Đang tải kết quả scan…` → `Loading scan results…`
- No-findings primary: `Chưa có findings cho run này.` → `No findings for this run.`
- No-findings secondary: `Có thể artifacts đã hết hạn...` → `Artifacts may have expired (retention: 1 day) or CI has not triggered a webhook.`
- Detail panel empty state: `Đang tải…` / `Chọn một pipeline run để xem kết quả` → `Loading…` / `Select a pipeline run to view results`

## Verification Results

```
npx tsc --noEmit         → 0 errors (PASS)
grep "Đang|Xoá|Lỗi|Chọn" → 0 matches (PASS)
grep "fontWeight: 700" KPI cards → 0 matches (PASS)
grep "filteredRuns" count → 5 occurrences (PASS)
grep "All branches"       → 1 match (PASS)
grep "formatDuration"     → 2 matches (definition + call site) (PASS)
grep "SeverityBar"        → 2 matches (import + usage) (PASS)
backend pytest (13 tests) → 13 passed (PASS)
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

**RunSummaryStrip SeverityBar counts are hardcoded zeros** (`{ critical: 0, high: 0, medium: 0, low: 0 }`). The plan specifies this as intentional for Phase 02 — real severity counts from findings would require additional state/API work tracked in a future plan. The SeverityBar renders a muted bar for zero-total input automatically (per Charts.tsx implementation). This stub is noted in the plan objective and is not blocking for PIPE-05 acceptance.

## Threat Flags

No new threat surface introduced. All branch names rendered via JSX string content (React auto-escapes). Branch filter is purely client-side on already-fetched data (T-02-04, T-02-06 accepted per threat register).

## Self-Check

- [x] `dashboard/src/pages/Pipelines.tsx` modified — verified via grep
- [x] Task 1 commit `817ac48` exists — verified via git log
- [x] Task 2 commit `5ba60b3` exists — verified via git log
- [x] TypeScript clean — `npx tsc --noEmit` exits 0
- [x] No Vietnamese strings remaining — grep returns zero matches

## Self-Check: PASSED

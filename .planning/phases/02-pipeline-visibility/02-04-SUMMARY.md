---
phase: 02-pipeline-visibility
plan: "04"
subsystem: dashboard/pipelines
tags: [pipe-05, finding-counts, severity-bar, gap-closure]
dependency_graph:
  requires: [02-03]
  provides: [PIPE-05]
  affects: [dashboard/src/pages/Pipelines.tsx]
tech_stack:
  added: []
  patterns: [cache-map-state, iife-in-jsx, demand-fetch-on-selection]
key_files:
  modified:
    - dashboard/src/pages/Pipelines.tsx
decisions:
  - findingCountCache dependency intentionally omitted from useEffect deps array to prevent infinite loop; cache-hit guard inside effect provides idempotency
  - IIFE pattern used in renderRunRow to avoid introducing a named sub-component
  - Error path caches zeros rather than leaving entry absent so failed runs do not re-fetch on every render
metrics:
  duration: "~10 minutes"
  completed: "2026-04-29"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 02 Plan 04: PIPE-05 Finding Count Gap Closure Summary

Real per-run finding counts wired to SeverityBar via `findingCountCache` Map state populated from `api.github.runFindings` on run selection, replacing hardcoded zero stub.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add findingCountCache state and selectedId useEffect | 9459318 | dashboard/src/pages/Pipelines.tsx |
| 2 | Wire SeverityBar to cache and add tool name tags | d54eb6c | dashboard/src/pages/Pipelines.tsx |

## What Was Built

**Task 1:** Added `findingCountCache` (Map state) and `loadingCounts` (Set state) to `PagePipelines`. A `useEffect` keyed on `selectedId` fetches `api.github.runFindings(selectedId)` when a run is selected and the run's counts are not yet cached. The effect tallies findings by severity (`critical`/`high`/`medium`/`low`) and collects unique tool names. On error, zeros are cached to prevent retry loops. `loadingCounts` tracks in-flight requests.

**Task 2:** Replaced the hardcoded `<SeverityBar counts={{ critical: 0, high: 0, medium: 0, low: 0 }} />` prop in `renderRunRow` with an IIFE that reads `findingCountCache.get(r.id)`, falls back to zeros while loading, renders tool name tags as `tool-tag` chips when findings exist, and shows a loading indicator (`…`) while the fetch is in flight. Duration display unchanged.

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

- `SeverityBar counts={{ critical: 0` in Pipelines.tsx: NONE (static prop gone)
- `findingCountCache.get(r.id)` in renderRunRow: 1 line (correct)
- `cached.tools` references: 2 lines (guard + map)
- `isLoadingThis` references: 2 lines (declaration + render)
- TypeScript `npx tsc --noEmit`: CLEAN (0 errors)

## Known Stubs

None — PIPE-05 gap is fully closed. SeverityBar now receives real counts from the API.

## Threat Surface Scan

No new network endpoints or auth paths introduced. The `findingCountCache` Map is in component state only, never serialized. The `has(selectedId)` guard (T-02-04-02) ensures at most one in-flight request per unique run ID.

## Self-Check

- [x] dashboard/src/pages/Pipelines.tsx modified and committed
- [x] Commit 9459318 exists (Task 1)
- [x] Commit d54eb6c exists (Task 2)
- [x] TypeScript CLEAN
- [x] SUMMARY.md created

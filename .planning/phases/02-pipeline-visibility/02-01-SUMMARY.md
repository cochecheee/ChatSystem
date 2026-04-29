---
phase: 02-pipeline-visibility
plan: "01"
subsystem: backend-api, frontend-types, test-suite
tags: [bug-fix, typescript-types, pytest, pipeline-visibility]
dependency_graph:
  requires: []
  provides:
    - "GET /github/runs returns all statuses (no status filter by default)"
    - "WorkflowRun TypeScript type includes updated_at optional field"
    - "PIPE-01/PIPE-02/PIPE-03 pytest regression guards installed"
  affects:
    - dashboard/src/pages/Pipelines.tsx
tech_stack:
  added: []
  patterns:
    - "FastAPI query param default changed from 'completed' to '' to pass all statuses"
    - "Frontend api method signature uses optional branch param instead of hardcoded status"
key_files:
  created: []
  modified:
    - mcp/src/api/artifacts.py
    - dashboard/src/api/client.ts
    - dashboard/src/types/index.ts
    - mcp/tests/test_main.py
    - mcp/tests/test_github_client.py
decisions:
  - "Empty string status default chosen over None to match existing github_client.py 'if status' guard pattern"
  - "Frontend runs() signature uses optional branch param — callers in Pipelines.tsx pass no args (valid as-is)"
metrics:
  duration: "~8 minutes"
  completed_date: "2026-04-29"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 5
---

# Phase 02 Plan 01: Status Bug Fix and Wave 0 Test Stubs Summary

**One-liner:** Removed two-location `status='completed'` hardcode so the pipeline page receives all GitHub workflow run statuses including `in_progress`; added `updated_at` TypeScript field; installed 3 pytest regression guards for PIPE-01/02/03.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix status default in backend route and frontend client | 50ace5b | mcp/src/api/artifacts.py, dashboard/src/api/client.ts |
| 2 | Add updated_at to WorkflowRun type and install Wave 0 test stubs | 6e8e11c | dashboard/src/types/index.ts, mcp/tests/test_main.py, mcp/tests/test_github_client.py |

## What Was Built

### Task 1: Bug Fix — status='completed' Hardcode Removed

**mcp/src/api/artifacts.py (line 82):** Changed `status: str = "completed"` to `status: str = ""` in the `list_github_runs` FastAPI route. With an empty string default, `github_client.list_workflow_runs` skips adding `status` to the GitHub API params dict (guarded by `if status:` at line 48 of github_client.py), so GitHub returns all runs regardless of status.

**dashboard/src/api/client.ts (line 53):** Replaced `runs: (status = 'completed') => get<WorkflowRun[]>('/github/runs', { status })` with `runs: (branch?: string) => get<WorkflowRun[]>('/github/runs', branch ? { branch } : {})`. Frontend no longer sends `status=completed` as a query param. The optional `branch` parameter enables future branch filtering without a signature break.

### Task 2: Type Update and Test Stubs

**dashboard/src/types/index.ts:** Added `updated_at?: string` to `WorkflowRun` interface immediately after `created_at`. This field is returned by the GitHub API and needed for run duration calculation in future plans.

**mcp/tests/test_main.py:** Appended `test_github_runs_all_statuses` — patches `GitHubClient.list_workflow_runs`, calls `GET /github/runs` with no params, asserts both `completed` and `in_progress` runs are returned, and verifies the backend calls the client with `status=""`.

**mcp/tests/test_github_client.py:** Appended two tests:
- `test_branch_filter_param` — verifies `list_workflow_runs` passes branch as a URL query param and does NOT add status to params when empty
- `test_no_status_param_when_empty` — verifies empty status string is not forwarded to GitHub API

## Verification Results

```
mcp pytest suite: 13 passed in 0.26s (0 failures)
TypeScript tsc --noEmit: 0 errors
grep 'status: str = "completed"' artifacts.py: 0 matches
grep "status = 'completed'" client.ts: 0 matches
grep 'updated_at' types/index.ts: 1 match (updated_at?: string)
```

## Deviations from Plan

None — plan executed exactly as written. All 5 target files modified per spec. All acceptance criteria verified.

## Known Stubs

None — this plan removes a hardcoded stub (`status='completed'`) rather than introducing stubs.

## Threat Flags

No new security-relevant surface introduced. Changes are internal param defaults and optional TypeScript fields. Threat register items T-02-01 (branch param injection via params dict), T-02-02 (unauthenticated route — accepted pre-existing posture), and T-02-03 (XSS — React JSX escaping) remain as-accepted in the plan's threat model.

## Self-Check: PASSED

- mcp/src/api/artifacts.py: modified (status default empty)
- dashboard/src/api/client.ts: modified (runs signature changed)
- dashboard/src/types/index.ts: modified (updated_at added)
- mcp/tests/test_main.py: modified (test_github_runs_all_statuses appended)
- mcp/tests/test_github_client.py: modified (test_branch_filter_param + test_no_status_param_when_empty appended)
- Commit 50ace5b: fix(02-01): remove hardcoded status=completed from backend route and frontend client
- Commit 6e8e11c: feat(02-01): add updated_at to WorkflowRun type and install Wave 0 pytest stubs

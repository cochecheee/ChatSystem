---
phase: 02
slug: pipeline-visibility
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-29
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (backend)** | pytest + pytest-asyncio (`mcp/pytest.ini`: `asyncio_mode = auto`) |
| **Framework (frontend)** | Playwright (`dashboard/playwright.config.ts`) |
| **Config file (backend)** | `mcp/pytest.ini` |
| **Config file (frontend)** | `dashboard/playwright.config.ts` |
| **Quick run command** | `cd mcp && python -m pytest tests/test_main.py tests/test_github_client.py -x -q` |
| **Full suite command** | `cd mcp && python -m pytest -x -q` |
| **E2E command** | `cd dashboard && npm run test:e2e` |
| **Estimated runtime** | ~10 seconds (backend unit) |

---

## Sampling Rate

- **After every task commit:** Run `cd mcp && python -m pytest tests/test_main.py tests/test_github_client.py -x -q`
- **After every plan wave:** Run `cd mcp && python -m pytest -x -q`
- **Before `/gsd-verify-work`:** Full backend suite green + manual Playwright smoke on Pipelines page
- **Max feedback latency:** ~10 seconds (backend unit suite)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | PIPE-01, PIPE-03 | — | `status` param omitted → all runs returned | unit | `pytest tests/test_main.py -k "test_github_runs" -x` | ❌ Wave 0 | ⬜ pending |
| 02-01-02 | 01 | 1 | PIPE-02 | T-branch-inject | branch param URL-encoded via httpx params dict | unit | `pytest tests/test_github_client.py -k "test_branch_filter" -x` | ❌ Wave 0 | ⬜ pending |
| 02-01-03 | 01 | 1 | PIPE-05 | — | updated_at field present in API response type | unit | `pytest tests/test_main.py -k "test_github_runs" -x` | ❌ Wave 0 | ⬜ pending |
| 02-02-01 | 02 | 2 | PIPE-02 | — | Branch filter select renders + filters runs | manual | Playwright smoke — select branch, verify run list narrows | ❌ Wave 0 | ⬜ pending |
| 02-02-02 | 02 | 2 | PIPE-05 | — | RunSummaryStrip shows tools + severity bar | manual | Playwright smoke — select run, verify strip visible | ❌ Wave 0 | ⬜ pending |
| 02-03-01 | 03 | 2 | PIPE-04 | — | TrendCard visible with ≥ 2 data points | manual | Playwright smoke — verify TrendCard renders | ❌ Wave 0 | ⬜ pending |
| 02-03-02 | 03 | 2 | PIPE-03 | — | LiveIndicator shown when in-progress run exists | manual | Manual: trigger a run, verify live dot appears | ❌ Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `mcp/tests/test_main.py::test_github_runs_all_statuses` — covers PIPE-01, PIPE-03 (status omission returns all runs)
- [ ] `mcp/tests/test_github_client.py::test_branch_filter_param` — covers PIPE-02 backend (branch param forwarded correctly)
- [ ] Frontend Playwright e2e stubs: no existing `tests/e2e/` directory in dashboard — acceptable; manual smoke covers Phase 02

*If the above pytest stubs are installed as part of plan 02-01, Wave 0 is satisfied for backend requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Branch filter narrows pipeline list | PIPE-02 | No Playwright e2e suite in dashboard | Open /pipelines, select a branch from filter, verify run count decreases |
| RunSummaryStrip shows tools + severity bar on selected run | PIPE-05 | No Playwright e2e suite | Click a run row, verify tool tags and severity bar appear below run name |
| TrendCard renders with ≥ 2 data points | PIPE-04 | Chart render is visual | Open /pipelines with > 1 run, verify AreaTrend chart visible |
| LiveIndicator shows when in-progress run exists | PIPE-03 | Requires live GitHub run | Trigger a GitHub Actions workflow, refresh page within 30s window |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

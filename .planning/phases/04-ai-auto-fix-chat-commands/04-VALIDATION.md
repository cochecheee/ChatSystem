---
phase: 4
slug: ai-auto-fix-chat-commands
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-29
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | backend/pytest.ini or pyproject.toml |
| **Quick run command** | `cd backend && pytest tests/ -x -q` |
| **Full suite command** | `cd backend && pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && pytest tests/ -x -q`
- **After every plan wave:** Run `cd backend && pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | CMD-01 | — | N/A | unit | `pytest tests/test_command_service.py -x -q` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | CMD-02 | — | N/A | unit | `pytest tests/test_command_service.py -x -q` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | CMD-03 | — | N/A | unit | `pytest tests/test_command_service.py -x -q` | ❌ W0 | ⬜ pending |
| 04-01-04 | 01 | 1 | CMD-04 | — | N/A | unit | `pytest tests/test_command_service.py -x -q` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | FIX-01 | — | InjectionGuardrail applied to /fix endpoint | unit | `pytest tests/test_auto_fix_service.py -x -q` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 1 | FIX-02 | — | patch cached in raw_data["pending_fix"] | unit | `pytest tests/test_auto_fix_service.py -x -q` | ❌ W0 | ⬜ pending |
| 04-02-03 | 02 | 2 | FIX-03 | — | N/A | integration | `pytest tests/test_fix_endpoints.py -x -q` | ❌ W0 | ⬜ pending |
| 04-03-01 | 03 | 2 | FIX-04 | — | N/A | manual | See Manual-Only section | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_command_service.py` — stubs for CMD-01, CMD-02, CMD-03, CMD-04
- [ ] `backend/tests/test_auto_fix_service.py` — stubs for FIX-01, FIX-02
- [ ] `backend/tests/test_fix_endpoints.py` — stubs for FIX-03

*If framework not installed: `pip install pytest pytest-asyncio httpx`*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Diff preview renders in dashboard before push | FIX-04 | UI interaction required | 1. Trigger /fix on a known finding, 2. Confirm DiffView renders +/- lines with correct colors, 3. Click "Push PR" and verify PR created on GitHub |
| PR branch created on GitHub | FIX-04 | GitHub API side effect | Check GitHub repo for new branch and open PR after fix approval |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

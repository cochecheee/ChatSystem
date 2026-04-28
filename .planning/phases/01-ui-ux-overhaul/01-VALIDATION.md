---
phase: 1
slug: ui-ux-overhaul
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-28
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | vitest (frontend) |
| **Config file** | `dashboard/vite.config.ts` |
| **Quick run command** | `cd dashboard && npm run type-check` |
| **Full suite command** | `cd dashboard && npm run build` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd dashboard && npm run type-check`
- **After every plan wave:** Run `cd dashboard && npm run build`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 1 | UI-01 | — | N/A | manual | `grep -r "notify\|toast\|Toaster" dashboard/src --include="*.tsx" --include="*.ts"` | ✅ | ⬜ pending |
| 1-01-02 | 01 | 1 | UI-02 | — | N/A | manual | `grep -c "\-\-surface-1\|\-\-surface-2" dashboard/src/tokens.css` | ✅ | ⬜ pending |
| 1-01-03 | 01 | 1 | UI-02 | — | N/A | build | `cd dashboard && npm run build` | ✅ | ⬜ pending |
| 1-02-01 | 02 | 2 | UI-03 | — | N/A | manual | `grep -rc "style={{" dashboard/src/pages --include="*.tsx"` | ✅ | ⬜ pending |
| 1-02-02 | 02 | 2 | UI-02 | — | N/A | build | `cd dashboard && npm run build` | ✅ | ⬜ pending |
| 1-02-03 | 02 | 2 | UI-03 | — | N/A | manual | visual inspection all 5 pages render without JS errors | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- Existing vitest/build infrastructure covers phase requirements.

*Existing infrastructure covers all phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| No toast notifications appear on any page | UI-01 | Visual — no E2E test for absence of popup | Load each of 5 pages, trigger an action that previously caused a toast (e.g., approve a finding), verify no popup appears |
| GitHub-style visual consistency | UI-02 | Visual — requires human judgment | Compare each page against GitHub.com reference: Inter font loaded, consistent spacing, no broken backgrounds |
| No redundant/dead UI elements | UI-03 | Structural audit | Review each page for hidden/unused components, commented-out sections, duplicated state |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

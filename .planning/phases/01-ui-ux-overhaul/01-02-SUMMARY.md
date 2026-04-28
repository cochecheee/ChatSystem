---
phase: 01-ui-ux-overhaul
plan: "02"
subsystem: dashboard
tags: [design-system, alert-banner, css-tokens, components, react, toast-removal]
dependency_graph:
  requires:
    - dashboard/src/components/AlertBanner.tsx (from 01-01)
    - dashboard/src/components/Badge.tsx (from 01-01)
    - dashboard/src/components/StatusDot.tsx (from 01-01)
    - dashboard/src/tokens.css --surface-1/2 aliases (from 01-01)
  provides:
    - dashboard/src/pages/Chat.tsx (AlertBanner for command/report feedback)
    - dashboard/src/pages/Reports.tsx (AlertBanner for download error)
    - dashboard/src/pages/Settings.tsx (AlertBanner + StatusDot + Badge in health banner)
    - dashboard/src/pages/Vulns.tsx (Badge in SevChip)
  affects:
    - dashboard/src/components/modals/ActionDialog.tsx
tech_stack:
  added: []
  patterns:
    - Local state + AlertBanner replacing addMsg() AI chat messages for command feedback
    - setReportStatus with downloadUrl for deferred report download action
    - StatusDot + Badge replacing inline dot div and chip span in health banner
    - Badge wrapping SevChip to eliminate raw className chip construction
key_files:
  created: []
  modified:
    - dashboard/src/pages/Chat.tsx
    - dashboard/src/pages/Reports.tsx
    - dashboard/src/pages/Settings.tsx
    - dashboard/src/pages/Vulns.tsx
    - dashboard/src/components/modals/ActionDialog.tsx
decisions:
  - AlertBanner for cmdStatus and reportStatus inserted between chat header and .ai-messages div (after the header border-bottom, before message list)
  - reportLoading AlertBanner shown as info type while report is being generated; replaced with success/error reportStatus on completion
  - handleApproveConfirm and handleRevokeConfirm wrapped in try/catch to support setCmdStatus on error (previously no error handling existed in these handlers)
  - SevChip kept as a wrapper function but now delegates to Badge rather than using raw span — preserves call sites unchanged
  - Badge lacks style prop so marginLeft:'auto' applied via wrapping span in Settings health banner
metrics:
  duration: "~8 minutes"
  completed: "2026-04-28"
  tasks_completed: 2
  tasks_total: 2
  files_created: 0
  files_modified: 5
  files_deleted: 0
---

# Phase 1 Plan 02: Page Cleanup Sweep Summary

**One-liner:** AlertBanner wired into Chat (7 notify sites → cmdStatus/reportStatus state), Reports (downloadError div), and Settings (form error + health banner StatusDot/Badge); Vulns SevChip upgraded to Badge; zero var(--surface-1) references remaining in any .tsx file.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Replace all Chat.tsx notify calls with local state + AlertBanner | 1058e31 | dashboard/src/pages/Chat.tsx |
| 2 | Upgrade Reports.tsx, Settings.tsx error displays + audit Vulns/Overview/Pipelines | 3499973 | 4 files modified |

## What Was Built

### Chat.tsx
- **AlertBanner import** added (replacing removed notify comment from 01-01)
- **State added:** `cmdStatus`, `reportStatus`, `reportLoading` with typed shapes
- **handleReport rewritten:** `addMsg` loading message → `setReportLoading(true)` on start; `setReportStatus({ type: 'success', msg, downloadUrl })` on success; `setReportStatus({ type: 'error', msg })` on error
- **executeCommand:** kept `replaceLastAi(text)` for AI response text; added `setCmdStatus` calls for success/error banner feedback
- **handleApproveConfirm/handleRevokeConfirm:** added try/catch with `setCmdStatus` for both success and error paths (previously had no error handling in these handlers)
- **AlertBanner renders:** three banners inserted after chat header — cmdStatus, reportStatus (with Tải xuống action button when downloadUrl present), reportLoading (info type)
- **LoginOverlay token fix:** `var(--surface-1)` → `var(--bg-elev)`, both `var(--surface-2)` instances → `var(--bg-muted)`

### Reports.tsx
- AlertBanner import added
- `downloadError` inline style div replaced with `<AlertBanner type="error" message={downloadError} onDismiss={() => setDownloadError('')} />`
- `var(--surface-2)` in select elements left as-is (token alias resolves it correctly)

### Settings.tsx
- AlertBanner, Badge, StatusDot imports added
- `AddProjectForm` error div replaced with AlertBanner
- Health banner inline dot div replaced with `<StatusDot status={...} />`
- Health chip `<span className="chip dot ...">` replaced with `<Badge variant={...}>` wrapped in `<span style={{ marginLeft: 'auto' }}>` (Badge lacks style prop)

### Vulns.tsx
- Badge import added
- `SevChip` function body: raw `<span className={...}>` replaced with `<Badge variant={sev as ...} dot>{sev}</Badge>` — all 4 SevChip call sites unchanged

### Audit Results
- **Overview.tsx:** No notify calls, no surface token references — clean, no changes needed
- **Pipelines.tsx:** No notify calls, no surface-1 references; existing `var(--surface-2)` at line 138 resolves via token alias — clean, no changes needed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing correctness] Fixed var(--surface-1) in ActionDialog.tsx**
- **Found during:** Task 2 verification (`grep -r "var(--surface-1)" dashboard/src/`)
- **Issue:** Plan verification criteria specify "zero matches for `var(--surface-1)` in any .tsx file" — ActionDialog.tsx had one remaining instance
- **Fix:** Replaced `var(--surface-1)` with `var(--bg-elev)` in modal container background
- **Files modified:** dashboard/src/components/modals/ActionDialog.tsx
- **Commit:** 3499973

**2. [Rule 2 - Missing error handling] Added try/catch to handleApproveConfirm and handleRevokeConfirm**
- **Found during:** Task 1 implementation review
- **Issue:** The original handlers had no error handling — API errors would throw uncaught exceptions. The plan's `setCmdStatus` replacement pattern requires a catch branch.
- **Fix:** Wrapped `api.chat.command(...)` calls in try/catch; catch sets `setCmdStatus({ type: 'error', msg: String(e) })`
- **Files modified:** dashboard/src/pages/Chat.tsx
- **Commit:** 1058e31

## Known Stubs

None — all components render real data from state. AlertBanner receives actual API error strings/success messages. No hardcoded empty values flow to UI.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundary changes. Error strings from API pass through `String(e)` before display (consistent with prior behavior).

## Self-Check

Files exist:
- dashboard/src/pages/Chat.tsx: FOUND
- dashboard/src/pages/Reports.tsx: FOUND
- dashboard/src/pages/Settings.tsx: FOUND
- dashboard/src/pages/Vulns.tsx: FOUND
- dashboard/src/components/modals/ActionDialog.tsx: FOUND

Commits:
- 1058e31: FOUND (Chat.tsx task)
- 3499973: FOUND (Reports/Settings/Vulns/ActionDialog task)

Verification results:
- `grep "notify\." dashboard/src/pages/`: zero matches
- `grep "var(--surface-1)" dashboard/src/`: zero matches
- `grep "AlertBanner" dashboard/src/pages/`: Chat.tsx, Reports.tsx, Settings.tsx
- `grep "StatusDot|Badge" dashboard/src/pages/Settings.tsx`: matched (both imported + used)
- `grep "Badge" dashboard/src/pages/Vulns.tsx`: matched (import + SevChip)
- `npm run build`: PASSED (0 TypeScript errors, vite build 171ms)

## Self-Check: PASSED

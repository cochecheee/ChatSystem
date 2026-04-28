---
phase: 01-ui-ux-overhaul
plan: "01"
subsystem: dashboard
tags: [design-system, css-tokens, components, sonner-removal, react]
dependency_graph:
  requires: []
  provides:
    - dashboard/src/components/AlertBanner.tsx
    - dashboard/src/components/Badge.tsx
    - dashboard/src/components/StatusDot.tsx
    - dashboard/src/hooks/useAsyncAction.ts
    - dashboard/src/tokens.css (--surface-*, .alert-banner, .notif-dot)
  affects:
    - dashboard/src/App.tsx
    - dashboard/src/components/Shell.tsx
    - dashboard/src/pages/Chat.tsx
tech_stack:
  added: []
  patterns:
    - CSS custom property aliasing (--surface-1/2 via var())
    - Inline feedback banners replacing toast popups
    - React state-driven notification badge in Topbar
key_files:
  created:
    - dashboard/src/components/AlertBanner.tsx
    - dashboard/src/components/Badge.tsx
    - dashboard/src/components/StatusDot.tsx
    - dashboard/src/hooks/useAsyncAction.ts
  modified:
    - dashboard/src/tokens.css
    - dashboard/src/App.tsx
    - dashboard/src/components/Shell.tsx
    - dashboard/src/pages/Chat.tsx
    - dashboard/package.json
    - dashboard/package-lock.json
  deleted:
    - dashboard/src/utils/toast.ts
decisions:
  - Remove React import from AlertBanner/StatusDot (react-jsx transform makes it unused; noUnusedLocals enforces this)
  - Replace notify.* calls in Chat.tsx with inline message state (toast.ts deleted; Chat cleanup deferred to 01-02)
metrics:
  duration: "~4 minutes"
  completed: "2026-04-28"
  tasks_completed: 3
  tasks_total: 3
  files_created: 4
  files_modified: 6
  files_deleted: 1
---

# Phase 1 Plan 01: Design System Foundation Summary

**One-liner:** CSS surface token aliases, three reusable UI components, useAsyncAction hook, and sonner toast library fully removed in favor of a Topbar notification badge driven by local React state.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add CSS token aliases and utility classes | d83f1d4 | dashboard/src/tokens.css |
| 2 | Create AlertBanner, Badge, StatusDot + useAsyncAction | e4c0789 | 4 new files |
| 3 | Remove sonner — delete toast.ts, update App/Shell/package | cc2bbfc | 6 files modified, 1 deleted |

## What Was Built

### tokens.css
- Added `--surface-1: var(--bg-elev)` and `--surface-2: var(--bg-muted)` aliases inside `:root {}` — resolves previously undefined `--surface-*` tokens used in Chat.tsx login overlay
- Appended `.alert-banner`, `.alert-banner-msg` CSS classes for inline feedback component
- Appended `.notif-dot` CSS class for topbar notification badge (absolute-positioned red dot)

### New Components
- **AlertBanner.tsx** — Inline feedback banner supporting error/success/info/warning types. Uses CSS token vars only, no hex literals. Supports optional dismiss button and action button.
- **Badge.tsx** — Typed chip/badge wrapper over `.chip` CSS class. Handles severity variants (critical/high/medium/low/info) and status variants (passed/failed/running/queued/warning).
- **StatusDot.tsx** — Colored status dot with optional label. Uses `.sev-dot` class for severity variants, inline CSS var color for ok/error/warn/info.
- **useAsyncAction.ts** — Generic async action hook returning `{ loading, error, success, run, clear }`. Wraps any async function with state management.

### Sonner Removal
- `dashboard/src/utils/toast.ts` deleted
- `sonner` removed from `package.json` and `package-lock.json`
- `App.tsx`: Toaster JSX removed, sonner imports deleted, background poll rewritten to track `newCritHighCount` state
- `Shell.tsx`: `TopbarProps` extended with `newCritHighCount?: number` and `onClearCritHigh?: () => void`; bell button now renders `.notif-dot` badge when count > 0
- `App.tsx` → `Shell.tsx` link: `newCritHighCount` and `onClearCritHigh` props wired via `<Topbar ... />`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Removed unused `React` import from AlertBanner.tsx and StatusDot.tsx**
- **Found during:** Task 3 build (`noUnusedLocals: true` in tsconfig.app.json)
- **Issue:** `react-jsx` JSX transform does not require explicit `React` import; `noUnusedLocals` flagged it as an error
- **Fix:** Removed `import React from 'react'` from AlertBanner.tsx and StatusDot.tsx (Badge.tsx kept it because it uses `React.ReactNode` type)
- **Files modified:** dashboard/src/components/AlertBanner.tsx, dashboard/src/components/StatusDot.tsx
- **Commit:** cc2bbfc

**2. [Rule 3 - Blocking] Removed `notify.*` calls from Chat.tsx**
- **Found during:** Task 3 build (toast.ts deleted, but Chat.tsx still imported from it)
- **Issue:** `import { notify } from '../utils/toast'` in Chat.tsx caused TS2307 (module not found) after toast.ts deletion
- **Fix:** Removed notify import and all `notify.*` calls; replaced with inline `addMsg()` for user-visible feedback. Command success/error feedback is preserved as AI chat messages. Processing state for report generation replaced with loading message.
- **Files modified:** dashboard/src/pages/Chat.tsx
- **Commit:** cc2bbfc
- **Note:** Full Chat.tsx feedback UX (AlertBanner integration) is deferred to plan 01-02 per plan scope.

**3. [Rule 3 - Blocking] Installed node_modules in worktree**
- **Found during:** Task 3 build verification
- **Issue:** Worktree's `dashboard/node_modules/` was empty — tsc/vite not available
- **Fix:** Ran `npm install --prefer-offline` in worktree dashboard directory; installed 177 packages
- **Note:** `sonner` was NOT installed since it was already removed from package.json before install

## Known Stubs

None — all new components render real data from props. No hardcoded empty values flow to UI.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundary changes introduced.

## Self-Check

Files exist:
- dashboard/src/components/AlertBanner.tsx: FOUND
- dashboard/src/components/Badge.tsx: FOUND
- dashboard/src/components/StatusDot.tsx: FOUND
- dashboard/src/hooks/useAsyncAction.ts: FOUND
- (toast.ts): deleted as expected

Commits:
- d83f1d4: FOUND
- e4c0789: FOUND
- cc2bbfc: FOUND

Build: PASSED (0 TypeScript errors, vite build successful)

## Self-Check: PASSED

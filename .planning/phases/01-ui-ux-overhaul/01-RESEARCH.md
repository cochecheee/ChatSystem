# Phase 1: UI/UX Overhaul - Research

**Researched:** 2026-04-28
**Domain:** React design system, CSS custom properties, inline notification patterns
**Confidence:** HIGH

---

## Summary

Phase 1 replaces a noisy, inconsistent UI with a clean GitHub-style design system. The codebase already has strong foundations: `tokens.css` defines a well-structured token system (fonts, colors, type scale, radii, shadows), and all layout primitives exist. The primary work is (1) removing `sonner` toast library and replacing every call site with inline state, (2) aliasing two undefined CSS variables (`--surface-1`, `--surface-2`) that silently break modals and forms, and (3) auditing pages for inline `style={{}}` props that bypass the token system.

The GitHub Primer design system's own guidance explicitly recommends abandoning toasts in favor of banners and inline messages. This validates the design direction and provides a clear replacement pattern: success is self-evident from UI state; failures use an inline `AlertBanner` component pinned near the action; background polling changes show a status dot in the topbar rather than a popup.

**Primary recommendation:** Remove `sonner`, add `--surface-1`/`--surface-2` aliases to `tokens.css`, create an `AlertBanner` component and a `useAsyncAction` hook for inline feedback, then sweep all 6 pages replacing `notify.*` calls with local state.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Design tokens (colors, type, space) | Browser / Client CSS | — | CSS custom properties; no server involvement |
| Notification feedback (was: toasts) | Browser / Client component state | — | Inline state in the component that triggers the action |
| Background polling status (crit/high count) | Browser / Client App.tsx | — | Already happens in App.tsx; replace notify with state |
| Reusable components (AlertBanner, Badge, StatusDot) | Browser / Client — shared components/ | — | Pure presentational; consumed by pages |
| Shell layout (Sidebar, Topbar) | Browser / Client | — | Static layout; only CSS token cleanup needed |

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| UI-01 | User sees no intrusive toast/popup notifications; status shown via subtle inline indicators | Sonner removal plan, AlertBanner pattern, useAsyncAction hook |
| UI-02 | Dashboard typography and layout follows GitHub-style design (Inter font, clean spacing, professional) | Existing Inter font already in tokens.css; token audit, `--surface-*` fix |
| UI-03 | All redundant/unused UI elements removed across Overview, Vulnerabilities, Pipelines, Chat, Reports pages | Inline style audit, undefined token fix, redundant element checklist |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React | 18.x (already installed) | Component model | Project baseline |
| TypeScript | (already installed) | Type safety | Project baseline |
| CSS Custom Properties | Native browser | Design tokens | Already the pattern in tokens.css |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Inter (Google Fonts or local) | N/A | GitHub-style sans-serif | Already declared in `--font-sans`; ensure it loads |
| JetBrains Mono | N/A | Monospace code/tags | Already declared in `--font-mono`; ensure it loads |

### Remove
| Library | Version | Reason |
|---------|---------|--------|
| sonner | ^2.0.7 | Toast-based notifications replaced by inline state; GitHub Primer explicitly recommends removing toasts |

**No new npm packages are needed for this phase.** All new components are hand-built with the existing CSS token system.

**Sonner removal verification:**
```bash
npm view sonner version  # currently 2.0.7
# After removal: grep -r "sonner\|Toaster\|toast\." dashboard/src/ --include="*.tsx" --include="*.ts"
```

---

## Architecture Patterns

### System Architecture Diagram

```
User action (button click / background poll)
          │
          ▼
  Component local state
  ┌─────────────────────────────────────────────┐
  │  loading: boolean                           │
  │  error: string | null                       │
  │  success: boolean                           │
  └─────────────────────────────────────────────┘
          │                      │
          ▼                      ▼
  <AlertBanner>           <StatusDot> in topbar
  (inline, near action)   (background poll result)
```

### Recommended Project Structure

```
dashboard/src/
├── tokens.css              # Single source of truth for all design tokens
├── components/
│   ├── Shell.tsx           # Sidebar + Topbar (minor cleanup)
│   ├── AlertBanner.tsx     # NEW: inline error/success/info banner
│   ├── StatusDot.tsx       # NEW: colored dot with optional label
│   ├── Badge.tsx           # NEW: severity/status chip (extract from tokens.css classes)
│   └── Icon.tsx            # Existing
├── hooks/
│   └── useAsyncAction.ts   # NEW: { run, loading, error, clearError }
└── pages/
    ├── Overview.tsx        # Remove notify.newFindings; add inline critHigh indicator
    ├── Chat.tsx            # Replace all notify.* with local state + AlertBanner
    ├── Pipelines.tsx       # Fix --surface-2 usage; no toast calls
    ├── Reports.tsx         # Fix --surface-2 usage; no toast calls
    ├── Vulns.tsx           # No toast calls (already clean)
    └── Settings.tsx        # Fix --surface-2 usage; no toast calls
```

### Pattern 1: useAsyncAction Hook

**What:** A reusable hook that wraps an async operation and exposes `{ loading, error, success, run, clear }` — the direct replacement for toast-based feedback.

**When to use:** Any button that triggers an API call (approve, revoke, generate report, run scan).

```typescript
// Source: ASSUMED pattern based on React docs and Primer guidance
// dashboard/src/hooks/useAsyncAction.ts
import { useCallback, useState } from 'react';

interface AsyncState {
  loading: boolean;
  error: string | null;
  success: boolean;
}

export function useAsyncAction<T>(
  fn: (...args: T[]) => Promise<void>
) {
  const [state, setState] = useState<AsyncState>({
    loading: false, error: null, success: false,
  });

  const run = useCallback(async (...args: T[]) => {
    setState({ loading: true, error: null, success: false });
    try {
      await fn(...args);
      setState({ loading: false, error: null, success: true });
    } catch (e) {
      setState({ loading: false, error: String(e), success: false });
    }
  }, [fn]);

  const clear = useCallback(() =>
    setState({ loading: false, error: null, success: false }), []);

  return { ...state, run, clear };
}
```

### Pattern 2: AlertBanner Component

**What:** An inline banner that shows error, success, or info state. Replaces all `notify.commandSuccess`, `notify.commandError`, `notify.report` toast calls.

**When to use:** Immediately below the action that triggered it (button group, form submit area).

```typescript
// Source: ASSUMED pattern based on Primer InlineMessage guidance
// dashboard/src/components/AlertBanner.tsx
interface AlertBannerProps {
  type: 'error' | 'success' | 'info' | 'warning';
  message: string;
  onDismiss?: () => void;
  action?: { label: string; onClick: () => void };
}

export function AlertBanner({ type, message, onDismiss, action }: AlertBannerProps) {
  // Maps to existing tokens:
  // error   → --err-fg / --err-bg
  // success → --ok-fg / --ok-bg
  // warning → --warn-fg / --warn-bg
  // info    → --fg-2 / --bg-muted
  const vars = {
    error:   { fg: 'var(--err-fg)',   bg: 'var(--err-bg)'  },
    success: { fg: 'var(--ok-fg)',    bg: 'var(--ok-bg)'   },
    warning: { fg: 'var(--warn-fg)',  bg: 'var(--warn-bg)' },
    info:    { fg: 'var(--fg-2)',     bg: 'var(--bg-muted)'},
  }[type];
  return (
    <div className="alert-banner" style={{ color: vars.fg, background: vars.bg }}>
      <span className="alert-banner-msg">{message}</span>
      {action && (
        <button className="btn ghost sm" onClick={action.onClick}>{action.label}</button>
      )}
      {onDismiss && (
        <button className="btn ghost sm" onClick={onDismiss}>×</button>
      )}
    </div>
  );
}
```

CSS to add to `tokens.css`:
```css
.alert-banner {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px;
  border-radius: var(--r-2);
  font-size: var(--ts-sm);
  margin-top: 8px;
}
.alert-banner-msg { flex: 1; }
```

### Pattern 3: Background Poll Status in Topbar

**What:** Replace `notify.newFindings(critHigh)` with a subtle indicator in the Topbar showing when new critical/high findings appear. No popup — a persistent count badge that the user notices naturally.

**When to use:** App.tsx already polls every 60s. Pass `critHighDelta` (new vs baseline) down to Topbar as a prop.

```typescript
// Source: ASSUMED — derived from existing App.tsx structure
// In App.tsx: expose newCritHigh state instead of calling notify
const [newCritHighCount, setNewCritHighCount] = useState(0);

// In Topbar: show a small badge on the bell icon when newCritHighCount > 0
{newCritHighCount > 0 && (
  <span className="notif-dot">{newCritHighCount}</span>
)}
```

CSS to add to `tokens.css`:
```css
.notif-dot {
  position: absolute; top: 2px; right: 2px;
  width: 16px; height: 16px; border-radius: 50%;
  background: var(--err-fg); color: white;
  font-size: 9px; font-weight: 700;
  display: grid; place-items: center;
  border: 2px solid var(--bg);
}
```

### Pattern 4: Fix Undefined CSS Tokens

**What:** `--surface-1` and `--surface-2` are used in `Chat.tsx`, `ActionDialog.tsx`, `Pipelines.tsx`, `Reports.tsx`, and `Settings.tsx` but are NOT defined in `tokens.css`. These silently render as transparent/unset in browsers.

**Fix:** Add aliases in `tokens.css`:
```css
:root {
  /* Aliases — resolve undefined --surface-* tokens used in older components */
  --surface-1: var(--bg-elev);    /* elevated surface = white/dark card */
  --surface-2: var(--bg-muted);   /* sunken input background */
}
```

**How to detect:** `grep -r "var(--surface" dashboard/src/` — currently returns 10 hits across 5 files.

### Anti-Patterns to Avoid

- **Inline `rgba(0,0,0,N)` hardcoded colors:** Found in `ActionDialog.tsx:64`, `Chat.tsx:48` for modal backdrops. Replace with a CSS class `.modal-overlay` using `background: rgba(0,0,0,.6)` defined once in tokens.css.
- **`style={{ background: 'var(--surface-2)' }}` inline:** Found in 6 places. Once the token alias is in tokens.css, convert these to className="..." using existing `.card`, `.code-block`, or a new `.input-surface` class.
- **`font-size: 12.5px` or `11.5px` magic numbers:** Several inline styles use fractional px outside the type scale. Replace with `var(--ts-sm)` (12px) or `var(--ts-xs)` (11px).
- **Calling `notify.*` without catching the replacement:** When removing notify calls, always provide a fallback error state. Don't just delete the call — replace it with `setError(msg)` or `useAsyncAction`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Inline alert styling | Custom per-component banner divs | `<AlertBanner>` component (to be created) | Consistency; already maps to existing CSS tokens |
| Status colors | Hardcoded hex in inline styles | Existing CSS tokens (`--ok-fg`, `--err-fg`, `--warn-fg`) | Already defined for both light + dark themes |
| Badge/chip rendering | Inline `<span>` with manual class strings | Extract `<Badge>` component wrapping `.chip` CSS class | Reduces class string mutation across 6 pages |
| Loading state per button | Custom spinner implementations | `.btn:disabled` + `loading` boolean pattern (already in tokens.css) | `opacity: 0.45` + `cursor: not-allowed` already handles it |

**Key insight:** The design system already exists in `tokens.css`. The work is extraction (wrapping CSS classes into typed React components) and removal (toast library + undefined tokens).

---

## Common Pitfalls

### Pitfall 1: Removing notify without replacing async feedback
**What goes wrong:** Developer deletes `notify.commandError(msg)` from Chat.tsx but adds no replacement — user gets no feedback when `/scan` or `/approve` fails.
**Why it happens:** notify calls are 1-liners; the replacement requires local state + JSX.
**How to avoid:** For every `notify.*` deletion, check the surrounding try/catch and add `setError(String(e))` + render `<AlertBanner>`.
**Warning signs:** Any catch block that is now empty after removing notify.

### Pitfall 2: --surface-1 / --surface-2 undefined tokens left unfixed
**What goes wrong:** Modals (ActionDialog, Chat login) render with transparent background — content is unreadable.
**Why it happens:** These tokens were used in components but never added to tokens.css.
**How to avoid:** Add aliases as the FIRST task in 01-01, before touching any component.
**Warning signs:** `grep "var(--surface" dashboard/src/` returns results after plan completion.

### Pitfall 3: Inline styles accumulating during "cleanup"
**What goes wrong:** Developer replaces a toast with inline JSX but writes `style={{ color: 'var(--err-fg)', background: 'var(--err-bg)' }}` instead of using AlertBanner.
**Why it happens:** Fast path feels simpler; component doesn't exist yet.
**How to avoid:** Create AlertBanner in 01-01 before doing the page sweep in 01-02.

### Pitfall 4: Dark theme regression from hardcoded colors
**What goes wrong:** Replacing inline styles with class names that only work in light theme.
**Why it happens:** tokens.css has `[data-theme="dark"]` overrides; hardcoded hex values ignore this.
**How to avoid:** ONLY use CSS custom property tokens in new CSS. Never write hex or rgba in component CSS unless it's the single `.modal-overlay` backdrop exception.

### Pitfall 5: Removing Toaster from App.tsx but leaving sonner import in toast.ts
**What goes wrong:** Build still bundles sonner; tree-shaker may not remove it fully.
**How to avoid:** Delete `dashboard/src/utils/toast.ts` entirely (not just remove its exports), remove sonner from package.json, and run `npm install` to clean lockfile.

---

## Code Examples

Verified patterns from codebase analysis:

### Current toast call sites (all must be replaced)
```
App.tsx:30         notify.newFindings(critHigh)           → App state + Topbar badge
Chat.tsx:122       notify.processing('Đang tạo báo cáo…') → setGeneratingReport(true)
Chat.tsx:136-137   notify.dismissProcessing() + notify.report() → AlertBanner with download action
Chat.tsx:145-146   notify.dismissProcessing() + notify.commandError() → AlertBanner type="error"
Chat.tsx:184       notify.commandSuccess(res.message)      → AlertBanner type="success" (auto-dismiss via useEffect)
Chat.tsx:199       notify.commandError(msg)                → AlertBanner type="error"
Chat.tsx:242       notify.commandSuccess(res.message)      → AlertBanner type="success"
Chat.tsx:250       notify.commandSuccess(res.message)      → AlertBanner type="success"
```

### Undefined tokens that must be fixed (grep confirms 10 occurrences)
```
--surface-1  →  var(--bg-elev)   (used in: ActionDialog, Chat.tsx LoginOverlay)
--surface-2  →  var(--bg-muted)  (used in: ActionDialog textarea, Chat inputs, Pipelines, Reports, Settings)
```

### Existing design tokens available (no new values needed)

All colors, type scale, and spacing are already defined in `tokens.css`. Key tokens for the new components:

```css
/* Status/feedback colors (light + dark defined) */
--ok-fg / --ok-bg       /* success green */
--err-fg / --err-bg     /* error red */
--warn-fg / --warn-bg   /* warning amber */
--fg-2 / --bg-muted     /* info/neutral */

/* Typography */
--ts-xs: 11px   /* badge labels */
--ts-sm: 12px   /* meta text, cells */
--ts-base: 13px /* body */
--ts-md: 15px   /* card headings */
--ts-lg: 20px   /* page headings */

/* Radii */
--r-1: 4px  --r-2: 6px  --r-3: 10px  --r-4: 14px

/* Fonts */
--font-sans: 'Inter', system-ui, -apple-system, sans-serif
--font-mono: 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `react-hot-toast` | `sonner` (already migrated) | Before this project | sonner is the current library — but BOTH are toast-based and must be removed |
| Toast for all feedback | Inline Banner + status state | GitHub Primer guidance (ongoing) | No floating popups; screen reader accessible; persistent until dismissed |
| Per-component inline style objects | CSS custom properties + class names | Primer/GitHub standard practice | Single source of truth; dark/light theme works automatically |

**Deprecated/outdated in this codebase:**
- `utils/toast.ts`: Entire file to be deleted. No migration — all call sites replaced with local state.
- `--surface-1`, `--surface-2` tokens: Not deprecated globally but need to be defined in tokens.css (they were used before being defined).
- Inline `style={{ fontSize: 12.5 }}` patterns: Should be replaced with `var(--ts-sm)` equivalents.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `useAsyncAction` hook pattern covers all Chat.tsx feedback scenarios | Architecture Patterns #1 | Some notify calls may need richer state (e.g., download URL from report); review Chat.tsx carefully before implementing |
| A2 | Adding `--surface-1: var(--bg-elev)` and `--surface-2: var(--bg-muted)` are semantically correct mappings | Pattern 4 | Modals may look slightly different than intended; verify visually after applying |
| A3 | `newCritHighCount` badge on the bell icon is sufficient replacement for `notify.newFindings` | Pattern 3 | Users may miss it; consider also changing the Vulns nav item count styling to draw attention |

---

## Open Questions

1. **Should `--surface-1`/`--surface-2` be kept as aliases or should all usages be migrated to `--bg-elev`/`--bg-muted`?**
   - What we know: 10 usage sites; both approaches are equivalent
   - What's unclear: Whether future components should continue using `--surface-*` naming
   - Recommendation: Add aliases for now (zero breakage risk); flag for cleanup in a later phase

2. **Does the theme toggle (light/dark) stay in Phase 1?**
   - What we know: Topbar has `onToggleTheme` prop; tokens.css has `[data-theme="dark"]` overrides
   - What's unclear: The phase goal is "GitHub-style" (light by default); dark mode is extra
   - Recommendation: Keep the toggle — it already works. Phase 1 just ensures both themes use only CSS tokens, not hardcoded values.

---

## Environment Availability

Step 2.6: SKIPPED — Phase 1 is CSS, TypeScript, and React component changes only. No external services, databases, or CLI tools beyond Node.js (already confirmed in git repo context).

---

## Validation Architecture

### How to verify design tokens are applied consistently

Visual inspection checklist (per page, run in browser with both light and dark theme):

- [ ] No white box appears where a colored surface is expected (would indicate undefined token falling back to white)
- [ ] Modal backdrop (ActionDialog, Chat login) is a semi-transparent overlay — not transparent
- [ ] Textarea/input fields in modals have a visible background
- [ ] All chip/badge text is legible in both themes
- [ ] KPI values use the correct type scale (large `--ts-xl`)
- [ ] Page headings use `--ts-lg` (20px), not larger/smaller

### How to verify no toast calls remain

```bash
# Run from project root: dashboard/
grep -r "notify\.\|toast\.\|Toaster\|from 'sonner'" \
  dashboard/src/ --include="*.tsx" --include="*.ts"
# Expected result after Phase 1: zero matches
```

### How to verify no undefined CSS token usage remains

```bash
grep -r "var(--surface-" dashboard/src/ --include="*.tsx" --include="*.ts" --include="*.css"
# Expected after Phase 1: zero matches (all replaced OR defined in tokens.css)
```

### How to verify no unused components

```bash
# Check for imported but never rendered components:
grep -r "import.*from.*components/" dashboard/src/pages/ --include="*.tsx"
# Cross-reference each import against JSX usage in the same file
# Flag any import where the component name does not appear in the JSX return

# Check for CSS classes defined but never used (approximation):
grep -o '\.[a-z][a-z-]*' dashboard/src/tokens.css | sort -u > /tmp/defined.txt
grep -roh 'className="[^"]*"' dashboard/src/ --include="*.tsx" | \
  grep -oE '"[^"]*"' | tr ' ' '\n' | sort -u > /tmp/used.txt
```

### Test Framework

| Property | Value |
|----------|-------|
| Framework | None configured (pure visual/grep verification) |
| Config file | N/A |
| Quick run command | See grep commands above |
| Full suite command | Manual visual review with light/dark toggle on all 5 pages |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| UI-01 | No toast/popup fires on any user action or background poll | grep | `grep -r "notify\.\|Toaster" dashboard/src/` | N/A (grep) |
| UI-02 | Inter font applied; no hardcoded hex colors outside tokens.css | grep | `grep -rn "#[0-9A-Fa-f]\{3,6\}" dashboard/src/ --include="*.tsx"` | N/A (grep) |
| UI-03 | No --surface-1/2 undefined; no components imported but unused | grep | `grep -r "var(--surface-" dashboard/src/` | N/A (grep) |

### Wave 0 Gaps

- [ ] No test files exist for this phase — all verification is grep-based and visual
- [ ] No vitest/jest configured in dashboard — this is acceptable; UI-only phase

---

## Security Domain

Security enforcement: The changes in this phase are purely presentational (CSS tokens, component composition, removing a toast library). No authentication, session management, data validation, or cryptography is introduced or modified. No ASVS categories apply to this phase.

---

## Sources

### Primary (HIGH confidence)
- [GitHub Primer accessibility guidance on toasts](https://primer.style/accessibility/toasts/) — confirmed GitHub recommends removing toasts; inline banner/banner patterns documented
- [GitHub Primer notification messaging patterns](https://primer.style/product/ui-patterns/notification-messaging/) — InlineMessage and Banner placement rules verified
- Codebase direct read: `dashboard/src/tokens.css` — full token inventory; `App.tsx`, `Shell.tsx`, `utils/toast.ts`, all 5 page files

### Secondary (MEDIUM confidence)
- [GitHub Primer typography](https://primer.style/foundations/typography/) — confirms rem-based scale and system font approach; project already uses Inter correctly
- [Primer CSS](https://github.com/primer/css) — confirms CSS-first, class-based approach aligns with project's custom CSS strategy

### Tertiary (LOW confidence — marked ASSUMED)
- `useAsyncAction` hook design is an ASSUMED pattern based on standard React idioms, not a Primer specification

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — codebase directly read; library versions confirmed via package.json
- Architecture: HIGH — all patterns derived from reading actual source files + Primer guidance
- Pitfalls: HIGH — all 5 pitfalls identified directly from codebase grep results, not hypothetical
- Token inventory: HIGH — tokens.css read in full

**Research date:** 2026-04-28
**Valid until:** 2026-06-01 (stable domain; tokens.css is the project's own file)

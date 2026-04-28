# Phase 1: UI/UX Overhaul - Pattern Map

**Mapped:** 2026-04-28
**Files analyzed:** 13
**Analogs found:** 13 / 13

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `dashboard/src/tokens.css` | config | transform | `dashboard/src/tokens.css` (self — add-only) | exact |
| `dashboard/src/components/AlertBanner.tsx` | component | request-response | `dashboard/src/pages/Settings.tsx` (health banner, lines 115–133) | role-match |
| `dashboard/src/components/Badge.tsx` | component | transform | `dashboard/src/tokens.css` `.chip` + `.sev-*` classes | exact |
| `dashboard/src/components/StatusDot.tsx` | component | transform | `dashboard/src/tokens.css` `.sev-dot` class (lines 770–775) | exact |
| `dashboard/src/App.tsx` | provider | event-driven | `dashboard/src/App.tsx` (self — remove Toaster, add state) | exact |
| `dashboard/src/utils/toast.ts` | utility | — | `dashboard/src/utils/toast.ts` (self — full deletion) | exact |
| `dashboard/src/hooks/useAsyncAction.ts` | hook | request-response | `dashboard/src/pages/Settings.tsx` AddProjectForm (lines 19–82) | role-match |
| `dashboard/src/pages/Chat.tsx` | component | request-response | `dashboard/src/pages/Chat.tsx` (self — replace notify calls) | exact |
| `dashboard/src/pages/Overview.tsx` | component | CRUD | `dashboard/src/pages/Overview.tsx` (self — layout cleanup) | exact |
| `dashboard/src/pages/Vulns.tsx` | component | CRUD | `dashboard/src/pages/Vulns.tsx` (self — minor cleanup) | exact |
| `dashboard/src/pages/Pipelines.tsx` | component | CRUD | `dashboard/src/pages/Pipelines.tsx` (self — fix --surface-2) | exact |
| `dashboard/src/pages/Reports.tsx` | component | CRUD | `dashboard/src/pages/Reports.tsx` (self — fix --surface-2) | exact |
| `dashboard/src/pages/Settings.tsx` | component | CRUD | `dashboard/src/pages/Settings.tsx` (self — fix --surface-2) | exact |
| `dashboard/src/components/Shell.tsx` | component | request-response | `dashboard/src/components/Shell.tsx` (self — CSS token cleanup) | exact |

---

## Pattern Assignments

### `dashboard/src/tokens.css` (config, add-only)

**Analog:** self

**Where to insert — after existing `:root { }` block, before the dark theme block (after line 68):**

```css
/* Aliases — resolve undefined --surface-* tokens used in components */
--surface-1: var(--bg-elev);   /* elevated surface = white/dark card */
--surface-2: var(--bg-muted);  /* sunken input background */
```

**New utility classes to append at end of file (after line 999):**

```css
/* AlertBanner — inline feedback component */
.alert-banner {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px;
  border-radius: var(--r-2);
  font-size: var(--ts-sm);
  margin-top: 8px;
}
.alert-banner-msg { flex: 1; }

/* Notification dot — topbar badge for background poll results */
.notif-dot {
  position: absolute; top: 2px; right: 2px;
  width: 16px; height: 16px; border-radius: 50%;
  background: var(--err-fg); color: white;
  font-size: 9px; font-weight: 700;
  display: grid; place-items: center;
  border: 2px solid var(--bg);
}
```

**Existing token references new components must use (lines 39–44):**
```css
--ok-fg: #2C6E3F;   --ok-bg: #DEEBE0;
--warn-fg: #8A6A1B; --warn-bg: #F6ECCD;
--err-fg: #8C1B1B;  --err-bg: #F6E1E1;
/* fg-2 / bg-muted serve as info/neutral */
--fg-2: #4A4844;    --bg-muted: #F4F3EF;
```

---

### `dashboard/src/components/AlertBanner.tsx` (component, request-response)

**Analog:** `dashboard/src/pages/Settings.tsx` — health banner section (lines 115–133)

The existing health banner in Settings.tsx is the closest inline-banner pattern in the codebase. It uses `.card`, inline style for the status dot, and a `.chip.dot` for the label. AlertBanner generalises this into a reusable component.

**Imports pattern — copy from `dashboard/src/components/Icon.tsx` (lines 1, 51):**
```typescript
import React from 'react';
// No external imports — pure CSS token component
```

**Existing inline-banner pattern from `dashboard/src/pages/Settings.tsx` (lines 115–133):**
```tsx
<div className="card" style={{ marginBottom: 20, padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
  <div style={{
    width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
    background: health === 'ok' ? 'var(--sev-low-fg)' : health === 'error' ? 'var(--sev-crit-fg)' : 'var(--fg-4)',
  }} />
  <div>
    <div style={{ fontSize: 13, fontWeight: 500 }}>Backend API — GET /health</div>
    <div className="muted" style={{ fontSize: 11 }}>...</div>
  </div>
  <span className={`chip dot ${health === 'ok' ? 'status-passed' : ...}`} style={{ marginLeft: 'auto', fontSize: 10 }}>
    {health}
  </span>
</div>
```

**New AlertBanner core pattern — uses `.alert-banner` class from tokens.css:**
```typescript
interface AlertBannerProps {
  type: 'error' | 'success' | 'info' | 'warning';
  message: string;
  onDismiss?: () => void;
  action?: { label: string; onClick: () => void };
}

export function AlertBanner({ type, message, onDismiss, action }: AlertBannerProps) {
  const vars = {
    error:   { fg: 'var(--err-fg)',  bg: 'var(--err-bg)'  },
    success: { fg: 'var(--ok-fg)',   bg: 'var(--ok-bg)'   },
    warning: { fg: 'var(--warn-fg)', bg: 'var(--warn-bg)' },
    info:    { fg: 'var(--fg-2)',    bg: 'var(--bg-muted)' },
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

**Button pattern to copy — `.btn.ghost.sm` from `dashboard/src/tokens.css` (lines 319, 324):**
```css
.btn.ghost { border-color: transparent; background: transparent; }
.btn.ghost:hover { background: var(--bg-muted); }
.btn.sm { padding: 4px 8px; font-size: var(--ts-xs); }
```

---

### `dashboard/src/components/Badge.tsx` (component, transform)

**Analog:** `.chip` class in `dashboard/src/tokens.css` (lines 327–346) + `.sev-*` modifier classes

**Existing chip pattern from `dashboard/src/tokens.css` (lines 327–346):**
```css
.chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 2px 7px;
  border-radius: 999px;
  font-size: var(--ts-xs);
  font-weight: 500;
  letter-spacing: -0.004em;
  background: var(--bg-muted);
  color: var(--fg-2);
  white-space: nowrap;
}
.chip.dot::before {
  content: ''; width: 6px; height: 6px; border-radius: 50%;
  background: currentColor;
}
.sev-critical { background: var(--sev-crit-bg); color: var(--sev-crit-fg); }
.sev-high     { background: var(--sev-high-bg); color: var(--sev-high-fg); }
.sev-medium   { background: var(--sev-med-bg);  color: var(--sev-med-fg);  }
.sev-low      { background: var(--sev-low-bg);  color: var(--sev-low-fg);  }
.sev-info     { background: var(--sev-info-bg); color: var(--sev-info-fg); }
```

**Existing usage in `dashboard/src/pages/Vulns.tsx` (lines 23–25) — the pattern Badge wraps:**
```tsx
function SevChip({ sev }: { sev: string }) {
  return <span className={`chip dot sev-${sev}`}>{sev}</span>;
}
```

**Badge component pattern — typed wrapper over `.chip`:**
```typescript
type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';
type StatusVariant = 'passed' | 'failed' | 'running' | 'queued' | 'warning';

interface BadgeProps {
  variant: Severity | StatusVariant | 'neutral';
  dot?: boolean;
  children: React.ReactNode;
}

export function Badge({ variant, dot = false, children }: BadgeProps) {
  // severity variants map to sev-* classes
  // status variants map to status-* classes
  const cls = ['critical','high','medium','low','info'].includes(variant)
    ? `sev-${variant}`
    : variant === 'neutral' ? '' : `status-${variant}`;
  return (
    <span className={`chip${dot ? ' dot' : ''} ${cls}`.trim()}>
      {children}
    </span>
  );
}
```

---

### `dashboard/src/components/StatusDot.tsx` (component, transform)

**Analog:** `.sev-dot` class family in `dashboard/src/tokens.css` (lines 770–775)

**Existing CSS pattern from `dashboard/src/tokens.css` (lines 770–775):**
```css
.sev-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.sev-dot.critical { background: var(--sev-crit-fg); }
.sev-dot.high     { background: var(--sev-high-fg); }
.sev-dot.medium   { background: var(--sev-med-fg); }
.sev-dot.low      { background: var(--sev-low-fg); }
.sev-dot.info     { background: var(--sev-info-fg); }
```

**StatusDot component pattern — typed wrapper over `.sev-dot`:**
```typescript
interface StatusDotProps {
  status: 'ok' | 'error' | 'warn' | 'info' | 'critical' | 'high' | 'medium' | 'low';
  label?: string;
  size?: number;
}

export function StatusDot({ status, label, size }: StatusDotProps) {
  // Map ok/error/warn to CSS token colors inline; severity maps to sev-dot class
  const isSev = ['critical','high','medium','low','info'].includes(status);
  const inlineColor = !isSev ? {
    ok:    'var(--ok-fg)',
    error: 'var(--err-fg)',
    warn:  'var(--warn-fg)',
    info:  'var(--fg-4)',
  }[status as 'ok'|'error'|'warn'|'info'] : undefined;

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      {isSev
        ? <span className={`sev-dot ${status}`} style={size ? { width: size, height: size } : undefined} />
        : <span style={{ width: size ?? 8, height: size ?? 8, borderRadius: '50%', background: inlineColor, flexShrink: 0 }} />
      }
      {label && <span style={{ fontSize: 'var(--ts-xs)', color: 'var(--fg-3)' }}>{label}</span>}
    </span>
  );
}
```

---

### `dashboard/src/hooks/useAsyncAction.ts` (hook, request-response)

**Analog:** `dashboard/src/pages/Settings.tsx` `AddProjectForm` (lines 19–82) — the closest existing example of local async action state pattern

**Existing async action state pattern from `dashboard/src/pages/Settings.tsx` (lines 19–42):**
```typescript
function AddProjectForm({ onAdded }: { onAdded: (p: Project) => void }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    if (!name.trim() || !url.trim()) { setError('...'); return; }
    setLoading(true);
    setError('');
    try {
      const p = await api.projects.create(name.trim(), url.trim());
      onAdded(p);
      setName(''); setUrl(''); setOpen(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };
```

**useAsyncAction hook — generalises the above try/catch/finally pattern:**
```typescript
import { useCallback, useState } from 'react';

interface AsyncState {
  loading: boolean;
  error: string | null;
  success: boolean;
}

export function useAsyncAction<T extends unknown[]>(
  fn: (...args: T) => Promise<void>
) {
  const [state, setState] = useState<AsyncState>({
    loading: false, error: null, success: false,
  });

  const run = useCallback(async (...args: T) => {
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

**Imports pattern — copy from `dashboard/src/pages/Chat.tsx` (line 1):**
```typescript
import { useCallback, useState } from 'react';
```

---

### `dashboard/src/App.tsx` (provider, event-driven)

**Analog:** self — targeted modifications

**Current imports to remove (lines 2, 11 — full lines to delete):**
```typescript
import { Toaster } from 'sonner';                                    // DELETE
import { notify, updateCritHighBaseline } from './utils/toast';       // DELETE
```

**Current poll logic to replace (lines 25–38):**
```typescript
// BEFORE — calls notify:
useEffect(() => {
  const fetch = () => {
    api.findings.list({ limit: 200 }).then(f => {
      setVulnCount(f.length);
      const critHigh = f.filter(x => x.severity === 'critical' || x.severity === 'high').length;
      notify.newFindings(critHigh);                    // REMOVE
      if (critHighRef.current === 0) updateCritHighBaseline(critHigh);  // REMOVE
      critHighRef.current = critHigh;
    }).catch(() => {});
  };
  ...
```

**New state to add alongside existing state declarations (after line 17):**
```typescript
const [newCritHighCount, setNewCritHighCount] = useState(0);
```

**Replacement poll logic pattern:**
```typescript
// AFTER — uses local state:
useEffect(() => {
  const fetchData = () => {
    api.findings.list({ limit: 200 }).then(f => {
      setVulnCount(f.length);
      const critHigh = f.filter(x => x.severity === 'critical' || x.severity === 'high').length;
      if (critHighRef.current !== 0 && critHigh > critHighRef.current) {
        setNewCritHighCount(critHigh - critHighRef.current);
      }
      if (critHighRef.current === 0) critHighRef.current = critHigh;
      else critHighRef.current = critHigh;
    }).catch(() => {});
  };
  ...
```

**JSX: remove Toaster, pass new prop to Topbar (lines 61–76):**
```tsx
// BEFORE:
<Topbar active={active} onNav={onNav} theme={theme} onToggleTheme={...} />
...
<Toaster position="bottom-right" richColors />   // DELETE entire line

// AFTER:
<Topbar active={active} onNav={onNav} theme={theme} onToggleTheme={...} newCritHighCount={newCritHighCount} onClearCritHigh={() => setNewCritHighCount(0)} />
// No <Toaster> at all
```

---

### `dashboard/src/utils/toast.ts` (utility — full deletion)

**Analog:** self — delete entire file

**Current content (all 31 lines) to be deleted in full.**

All call sites are in:
- `dashboard/src/App.tsx` lines 11, 30, 31 — replaced by state per App.tsx pattern above
- `dashboard/src/pages/Chat.tsx` lines 6, 122, 136–137, 145–146, 184, 199, 242, 250 — replaced by AlertBanner per Chat.tsx pattern below

After deletion, remove `sonner` from `package.json` dependencies and run `npm install`.

---

### `dashboard/src/pages/Chat.tsx` (component, request-response)

**Analog:** self — targeted modifications; `useAsyncAction` hook (new)

**Current import to remove (line 6):**
```typescript
import { notify } from '../utils/toast';    // DELETE
```

**New import to add:**
```typescript
import { AlertBanner } from '../components/AlertBanner';
```

**Existing local error/state pattern in `LoginOverlay` (lines 29–39) — the inline state pattern already used here, confirm it stays:**
```typescript
const [loading, setLoading] = useState(false);
const [error, setError] = useState('');
// ...
try { ... } catch (e) { setError(String(e)); setLoading(false); }
```

**handleReport replacements — lines 122, 136–137, 145–146:**
```typescript
// ADD state at top of PageChat():
const [reportStatus, setReportStatus] = useState<{ type: 'success' | 'error'; msg: string; downloadUrl?: string } | null>(null);
const [reportLoading, setReportLoading] = useState(false);

// REPLACE notify.processing (line 122):
setReportLoading(true);

// REPLACE notify.dismissProcessing() + notify.report() (lines 136–137):
setReportLoading(false);
setReportStatus({ type: 'success', msg: 'Báo cáo đã sẵn sàng', downloadUrl: url });

// REPLACE notify.dismissProcessing() + notify.commandError() (lines 145–146):
setReportLoading(false);
setReportStatus({ type: 'error', msg: `Lỗi tạo báo cáo: ${e}` });
```

**executeCommand replacements — lines 184, 199:**
```typescript
// ADD state at top of PageChat():
const [cmdStatus, setCmdStatus] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

// REPLACE notify.commandSuccess (line 184):
setCmdStatus({ type: 'success', msg: res.message });

// REPLACE notify.commandError (line 199):
setCmdStatus({ type: 'error', msg });
```

**handleApproveConfirm / handleRevokeConfirm replacements — lines 242, 250:**
```typescript
// REPLACE notify.commandSuccess(res.message) (lines 242, 250):
setCmdStatus({ type: 'success', msg: res.message });
```

**AlertBanner render location — insert in JSX below the chat header section, above `.ai-messages` div:**
```tsx
{cmdStatus && (
  <AlertBanner
    type={cmdStatus.type}
    message={cmdStatus.msg}
    onDismiss={() => setCmdStatus(null)}
  />
)}
{reportStatus && (
  <AlertBanner
    type={reportStatus.type}
    message={reportStatus.msg}
    onDismiss={() => setReportStatus(null)}
    action={reportStatus.downloadUrl ? { label: 'Tải lại', onClick: () => { /* re-trigger download */ } } : undefined}
  />
)}
```

**LoginOverlay: replace inline `style={{ background: 'var(--surface-1)' }}` (line 52) and `style={{ background: 'var(--surface-2)' }}` (lines 67, 79) with className equivalents using CSS token classes from tokens.css:**
```tsx
// line 52 — replace inline style background with --bg-elev reference:
style={{ background: 'var(--bg-elev)', border: '1px solid var(--line)', ... }}

// lines 67, 79 — replace var(--surface-2) with var(--bg-muted):
style={{ background: 'var(--bg-muted)', border: '1px solid var(--line)', ... }}
```

---

### `dashboard/src/components/Shell.tsx` (component, layout)

**Analog:** self — targeted modifications

**Topbar props interface to extend (lines 84–89):**
```typescript
// BEFORE:
interface TopbarProps {
  active: PageId;
  onNav: (id: PageId) => void;
  theme: string;
  onToggleTheme: () => void;
}

// AFTER — add two new optional props:
interface TopbarProps {
  active: PageId;
  onNav: (id: PageId) => void;
  theme: string;
  onToggleTheme: () => void;
  newCritHighCount?: number;
  onClearCritHigh?: () => void;
}
```

**Bell button pattern to update (lines 109–111) — add `.notif-dot` badge:**
```tsx
// BEFORE:
<button className="btn ghost" style={{ padding: 6 }}>
  <Icon name="bell" size={15} />
</button>

// AFTER — add notif-dot badge and position:relative:
<button className="btn ghost" style={{ padding: 6, position: 'relative' }} onClick={onClearCritHigh}>
  <Icon name="bell" size={15} />
  {(newCritHighCount ?? 0) > 0 && (
    <span className="notif-dot">{newCritHighCount}</span>
  )}
</button>
```

**user-chip inline style (line 73) — remove inline style, already handled by flex: 1:**
```tsx
// BEFORE:
<div style={{ flex: 1, minWidth: 0 }}>

// AFTER — extract to className or keep as-is (acceptable; not a token violation):
// This inline style is structural layout, not a design token override — acceptable to leave.
```

---

### `dashboard/src/pages/Overview.tsx` (component, CRUD)

**Analog:** self — layout cleanup; no toast calls exist here

**Existing page-header pattern to confirm is used (lines 46–61 confirm structure):**
```tsx
// Pattern already correct — uses className="content", "page-header", "h1", "sub"
// No notify.* calls exist in Overview.tsx — only cleanup needed is adding critHighDelta display
// if desired (optional; App.tsx Topbar badge is sufficient)
```

**Import pattern (lines 1–7) — confirm no sonner imports:**
```typescript
import { useEffect, useState } from 'react';
import { api } from '../api/client';
// ... no notify import — no changes needed beyond potential layout polish
```

---

### `dashboard/src/pages/Vulns.tsx` (component, CRUD)

**Analog:** self — already clean of toast calls

**Import pattern (lines 1–5) — no notify import, no changes needed:**
```typescript
import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import { Icon } from '../components/Icon';
import type { AnalysisResult, Finding, Project } from '../types';
import { SEVERITY_ORDER } from '../types';
```

**Existing SevChip pattern (lines 23–25) — this becomes the analog for Badge.tsx:**
```tsx
function SevChip({ sev }: { sev: string }) {
  return <span className={`chip dot sev-${sev}`}>{sev}</span>;
}
// After Badge.tsx is created, replace with: <Badge variant={sev} dot>{sev}</Badge>
```

---

### `dashboard/src/pages/Pipelines.tsx` (component, CRUD)

**Analog:** self — fix `--surface-2` usage

**Existing `var(--surface-2)` usage pattern to find and replace (search: `var(--surface-2)` or `var(--surface`):**
```typescript
// From Pipelines.tsx imports (lines 1–5):
import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { Icon } from '../components/Icon';
// No notify import — correct

// Token fix: once --surface-2 alias is added to tokens.css (points to --bg-muted),
// the existing inline style={{ background: 'var(--surface-2)' }} calls become valid automatically.
// No JSX edits required — only tokens.css alias addition fixes all Pipelines.tsx usages.
```

---

### `dashboard/src/pages/Reports.tsx` (component, CRUD)

**Analog:** self — fix `--surface-2` usage; existing downloadError state is already the correct pattern

**Existing inline-error pattern already present (lines 22–24, 48–56) — shows the pattern is already partially correct:**
```typescript
const [downloading, setDownloading] = useState(false);
const [downloadError, setDownloadError] = useState('');
// try/catch/finally with setDownloadError(String(e)) at line 70 — CORRECT pattern
// No notify.* calls — already clean
```

**select element using --surface-2 (lines 86–93):**
```tsx
<select style={{ background: 'var(--surface-2)', ... }}>
// Fixed automatically once --surface-2 alias is added to tokens.css
// Optional improvement: replace inline style with className from filter-toolbar
```

**Existing downloadError render pattern to upgrade to AlertBanner (in JSX below page-header):**
```tsx
// BEFORE (current inline approach):
{downloadError && <div style={{ color: 'var(--sev-crit-fg)', fontSize: 12 }}>{downloadError}</div>}

// AFTER — consistent with AlertBanner:
{downloadError && (
  <AlertBanner type="error" message={downloadError} onDismiss={() => setDownloadError('')} />
)}
```

---

### `dashboard/src/pages/Settings.tsx` (component, CRUD)

**Analog:** self — fix `--surface-2` in `AddProjectForm`

**Existing --surface-2 usage in AddProjectForm inputs (lines 53–56, 63–66):**
```tsx
<input style={{ background: 'var(--surface-2)', border: '1px solid var(--line)', ... }} />
// Fixed automatically once --surface-2 alias is added to tokens.css.
// Optionally replace with className="..." using .filter-toolbar select pattern from tokens.css line 899
```

**Existing error render in AddProjectForm (line 73) — upgrade to AlertBanner:**
```tsx
// BEFORE:
{error && <div style={{ color: 'var(--sev-crit-fg)', fontSize: 11 }}>{error}</div>}

// AFTER:
{error && <AlertBanner type="error" message={error} onDismiss={() => setError('')} />}
```

**Health status banner (lines 115–133) — already close to AlertBanner pattern; optionally refactor to use `<StatusDot>` for the dot + `<Badge>` for the chip:**
```tsx
// BEFORE:
<div style={{ width: 10, height: 10, borderRadius: '50%', background: health === 'ok' ? 'var(--sev-low-fg)' : ... }} />
<span className={`chip dot ${health === 'ok' ? 'status-passed' : ...}`}>

// AFTER:
<StatusDot status={health === 'ok' ? 'ok' : health === 'error' ? 'error' : 'info'} />
<Badge variant={health === 'ok' ? 'passed' : health === 'error' ? 'failed' : 'running'}>{health}</Badge>
```

---

## Shared Patterns

### Token Usage (CSS Custom Properties Only)
**Source:** `dashboard/src/tokens.css` lines 6–107
**Apply to:** Every new and modified file

Never write hex color values or `rgba()` in `.tsx` files except the single modal backdrop (`rgba(0,0,0,0.6)`). Always use `var(--token-name)`.

```css
/* Status feedback: */
var(--ok-fg) / var(--ok-bg)       /* success */
var(--err-fg) / var(--err-bg)     /* error */
var(--warn-fg) / var(--warn-bg)   /* warning */
var(--fg-2) / var(--bg-muted)     /* info/neutral */

/* Typography: */
var(--ts-xs)   /* 11px — badges, labels */
var(--ts-sm)   /* 12px — table cells, meta */
var(--ts-base) /* 13px — body */
var(--ts-md)   /* 15px — card headings */
var(--ts-lg)   /* 20px — page headings */

/* Layout: */
var(--r-1) var(--r-2) var(--r-3) var(--r-4)  /* 4/6/10/14px radii */
var(--line) var(--line-strong)                /* borders */
var(--bg-elev) var(--bg-muted) var(--bg-sunken)  /* surfaces */
```

### Local Async State Pattern
**Source:** `dashboard/src/pages/Settings.tsx` `AddProjectForm` (lines 19–82)
**Apply to:** `Chat.tsx`, any component with API-triggered actions

```typescript
// The three required state variables:
const [loading, setLoading] = useState(false);
const [error, setError] = useState<string | null>(null);
const [success, setSuccess] = useState(false);

// The required try/catch/finally shape:
try {
  setLoading(true); setError(null);
  await apiCall();
  setSuccess(true);
} catch (e) {
  setError(String(e));
} finally {
  setLoading(false);
}
```

### Component Imports
**Source:** `dashboard/src/components/Icon.tsx` (line 1), `dashboard/src/pages/Vulns.tsx` (lines 1–5)
**Apply to:** All new `.tsx` components

```typescript
// Standard import ordering used across the codebase:
import { useState, useEffect, ... } from 'react';      // 1. React hooks
import { api } from '../api/client';                    // 2. API client (if needed)
import { ComponentName } from '../components/Name';     // 3. Components
import type { TypeName } from '../types';               // 4. Types (type-only imports)
```

### Page Layout Structure
**Source:** `dashboard/src/pages/Settings.tsx` (lines 102–112), `dashboard/src/pages/Reports.tsx` (lines 76–82)
**Apply to:** All page components

```tsx
// Correct page shell — confirmed used in Settings and Reports:
return (
  <div className="content">
    <div className="page-header">
      <div>
        <h1 className="h1">Page Title</h1>
        <div className="sub">Subtitle text</div>
      </div>
      {/* optional action buttons */}
    </div>
    {/* page body */}
  </div>
);
```

### Modal Overlay (One Acceptable rgba Exception)
**Source:** `dashboard/src/components/modals/ActionDialog.tsx` (lines 61–66)
**Apply to:** Chat.tsx `LoginOverlay`, any modal components

```tsx
// The ONE approved place for rgba — modal backdrop:
<div style={{
  position: 'fixed', inset: 0, zIndex: 1000,
  background: 'rgba(0,0,0,0.6)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
}}>
  <div style={{
    background: 'var(--bg-elev)',   /* was: var(--surface-1) — now uses defined token */
    border: '1px solid var(--line)',
    borderRadius: 10,
    boxShadow: 'var(--shadow-pop)',  /* replace inline shadow with token */
  }}>
```

---

## No Analog Found

All 13 files have analogs or are self-modifications. No files require falling back to external patterns.

| File | Note |
|---|---|
| `dashboard/src/hooks/useAsyncAction.ts` | No hooks directory exists yet. Closest analog is `AddProjectForm` in Settings.tsx (inline pattern). Hook is a direct extraction of that pattern. |

---

## Metadata

**Analog search scope:** `dashboard/src/` — all `.tsx`, `.ts`, `.css` files
**Files scanned:** App.tsx, Shell.tsx, tokens.css, toast.ts, Icon.tsx, Chat.tsx, Overview.tsx, Vulns.tsx, Pipelines.tsx, Reports.tsx, Settings.tsx, ActionDialog.tsx, Charts.tsx
**Pattern extraction date:** 2026-04-28

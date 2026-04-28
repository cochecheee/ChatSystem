---
phase: 01-ui-ux-overhaul
reviewed: 2026-04-28T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - dashboard/src/components/AlertBanner.tsx
  - dashboard/src/components/Badge.tsx
  - dashboard/src/components/StatusDot.tsx
  - dashboard/src/hooks/useAsyncAction.ts
  - dashboard/src/tokens.css
  - dashboard/src/App.tsx
  - dashboard/src/components/Shell.tsx
  - dashboard/src/pages/Chat.tsx
  - dashboard/src/pages/Reports.tsx
  - dashboard/src/pages/Settings.tsx
  - dashboard/src/pages/Vulns.tsx
  - dashboard/src/components/modals/ActionDialog.tsx
findings:
  critical: 4
  warning: 9
  info: 5
  total: 18
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-04-28T00:00:00Z
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Reviewed 12 source files covering the UI/UX overhaul: design tokens, shared components (`AlertBanner`, `Badge`, `StatusDot`), a reusable hook (`useAsyncAction`), the app shell (`App.tsx`, `Shell.tsx`), and all four page components (`Chat.tsx`, `Reports.tsx`, `Settings.tsx`, `Vulns.tsx`) plus the shared `ActionDialog` modal.

The design-token layer and component primitives are clean. The majority of defects are concentrated in `Chat.tsx` and `App.tsx`: a memory-leaking object URL that is never revoked, role-based access control that is entirely client-side and trivially bypassed, a stale-closure bug in the polling effect, and several places where error states are silently swallowed or incorrectly presented to the user. There are also several accessibility gaps (interactive `div`s without keyboard handling) that affect usability for keyboard-only users.

---

## Critical Issues

### CR-01: Blob URL created in Chat.tsx is never revoked — memory leak guaranteed on every report download

**File:** `dashboard/src/pages/Chat.tsx:136`
**Issue:** `handleReport` creates a `URL.createObjectURL(blob)` and stores the URL in state (`reportStatus.downloadUrl`). The URL is never passed to `URL.revokeObjectURL`. Every time a report is downloaded the browser holds an unreleased reference to the entire blob in memory for the lifetime of the tab. The same pattern is also present in `Reports.tsx:69` — but there `revokeObjectURL` *is* called immediately after `a.click()`, creating a race condition where the download may not have started before the URL is revoked (some browsers handle this; others silently fail).

**Fix for Chat.tsx** — revoke the URL inside the download click handler:
```typescript
action={reportStatus.downloadUrl
  ? {
      label: 'Tải xuống',
      onClick: () => {
        const a = document.createElement('a');
        a.href = reportStatus.downloadUrl!;
        a.download = 'security-report.html';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(reportStatus.downloadUrl!);
        setReportStatus(r => r ? { ...r, downloadUrl: undefined } : null);
      },
    }
  : undefined}
```

**Fix for Reports.tsx:65-69** — append the anchor to the DOM so the click is reliable before revoking:
```typescript
const a = document.createElement('a');
a.href = url;
a.download = 'security-report.html';
document.body.appendChild(a);
a.click();
document.body.removeChild(a);
URL.revokeObjectURL(url); // safe: browser queues the download before this runs
```

---

### CR-02: Authentication is client-side only — role escalation requires zero server knowledge

**File:** `dashboard/src/pages/Chat.tsx:77-98`
**Issue:** `LoginOverlay` lets the user freely select their own role (`developer`, `security_lead`, `admin`) from a `<select>` before calling `api.chat.login(username, role)`. The role sent to the server is entirely user-controlled. Any user can self-promote to `admin` by simply changing the select value. If the backend trusts the role field from the JWT payload without validating it server-side against a user database, this is a trivial privilege escalation. Even if the backend does validate it, the UI provides no friction and actively invites abuse.

**Fix:** Remove the role selector from the login UI entirely. The server should return the role as part of the authenticated JWT response and the client should display (not set) it. If role selection is needed for a demo/dev environment, gate it behind an explicit environment flag:
```typescript
// Only show role picker in dev builds
{import.meta.env.DEV && (
  <select value={role} onChange={e => setRole(e.target.value)}>…</select>
)}
```

---

### CR-03: Stale closure in App.tsx polling effect — `critHighRef` comparison uses initial ref value

**File:** `dashboard/src/App.tsx:24-38`
**Issue:** The polling `useEffect` captures `critHighRef` at setup time. `critHighRef` is a ref, so reads of `.current` inside the closure are always live — that part is correct. However, the condition on line 29 reads:

```typescript
if (critHighRef.current !== 0 && critHigh > critHighRef.current) {
```

The guard `critHighRef.current !== 0` is intended to suppress the spurious first-run notification, but on the very first successful fetch `critHighRef.current` is `0`, so the guard fires correctly. On subsequent fetches where the count *drops* (findings resolved), `critHighRef.current` is updated to the lower value but `newCritHighCount` is never decremented. This means the notification dot accumulates indefinitely across polling cycles even after the user clears it and the count returns to normal. Additionally, the `critHighRef.current` assignment on line 32 happens inside `.then()` which runs after the component might have unmounted — there is no cleanup guard.

**Fix:** Track whether the component is still mounted and also reset `newCritHighCount` when the count drops:
```typescript
useEffect(() => {
  let mounted = true;
  const fetchData = () => {
    api.findings.list({ limit: 200 }).then(f => {
      if (!mounted) return;
      const critHigh = f.filter(x => x.severity === 'critical' || x.severity === 'high').length;
      if (critHighRef.current !== 0 && critHigh > critHighRef.current) {
        setNewCritHighCount(prev => prev + (critHigh - critHighRef.current));
      }
      critHighRef.current = critHigh;
      setVulnCount(f.length);
    }).catch(() => {});
  };
  fetchData();
  const id = setInterval(fetchData, 60_000);
  return () => { mounted = false; clearInterval(id); };
}, []);
```

---

### CR-04: `useAsyncAction` captures `fn` in a `useCallback` with `[fn]` dependency — causes infinite re-render loop when caller passes an inline function

**File:** `dashboard/src/hooks/useAsyncAction.ts:16-24`
**Issue:** `run` is memoized with `useCallback(..., [fn])`. When the caller passes an arrow function inline (the most natural usage pattern), `fn` is a new reference on every render, so `run` is also recreated every render. Any component that renders `run` into a `useEffect` dependency array or passes it as a prop will experience an infinite update loop. This is a correctness defect, not just a performance concern.

**Fix:** Use a ref to hold the latest `fn` so `run` can have a stable identity:
```typescript
export function useAsyncAction<T extends unknown[]>(
  fn: (...args: T) => Promise<void>
) {
  const fnRef = useRef(fn);
  useEffect(() => { fnRef.current = fn; });

  const [state, setState] = useState<AsyncState>({
    loading: false, error: null, success: false,
  });

  const run = useCallback(async (...args: T) => {
    setState({ loading: true, error: null, success: false });
    try {
      await fnRef.current(...args);
      setState({ loading: false, error: null, success: true });
    } catch (e) {
      setState({ loading: false, error: String(e), success: false });
    }
  }, []); // stable — never recreated

  const clear = useCallback(() =>
    setState({ loading: false, error: null, success: false }), []);

  return { ...state, run, clear };
}
```

---

## Warnings

### WR-01: `AlertBanner` has no ARIA role — screen readers cannot perceive error/success feedback

**File:** `dashboard/src/components/AlertBanner.tsx:16`
**Issue:** The banner renders a plain `<div>`. For `type="error"` and `type="warning"` it should carry `role="alert"` so assistive technologies announce it immediately when it appears. For `type="success"` and `type="info"` it should carry `role="status"`.

**Fix:**
```typescript
const role = (type === 'error' || type === 'warning') ? 'alert' : 'status';
return (
  <div className="alert-banner" role={role} aria-live={role === 'alert' ? 'assertive' : 'polite'}
       style={{ color: vars.fg, background: vars.bg }}>
```

---

### WR-02: Dismiss button in `AlertBanner` has no accessible label

**File:** `dashboard/src/components/AlertBanner.tsx:22`
**Issue:** The dismiss button renders the raw `×` character as its only content. Screen readers will announce "times" or "multiplication sign" rather than "Dismiss". This affects every usage of `AlertBanner` with `onDismiss`.

**Fix:**
```typescript
<button className="btn ghost sm" onClick={onDismiss} aria-label="Dismiss">×</button>
```

---

### WR-03: `StatusDot` renders `undefined` background when `status` is `'info'` and `isSev` is false

**File:** `dashboard/src/components/StatusDot.tsx:9-14`
**Issue:** `'info'` is listed in the `isSev` array at line 8, so `isSev` will be `true` for `status='info'`. However, the `StatusDotProps` type also accepts `'info'` as a non-severity status. If a caller passes `status="info"`, it hits the `isSev` branch and renders a `sev-dot info` span — but the CSS class `.sev-dot.info` is not defined in `tokens.css` (only `.sev-dot.critical`, `.sev-dot.high`, `.sev-dot.medium`, `.sev-dot.low`, `.sev-dot.info` — actually `.sev-dot.info` is defined at line 779). This is okay, but the inline fallback map on line 10 also contains an `info` key pointing to `var(--fg-4)` that can never be reached because `isSev` short-circuits it. Dead code that will confuse maintainers.

Additionally, if a new status value is passed that is neither in `isSev` nor in the inline map (e.g., a future `'unknown'` status), `inlineColor` will be `undefined` and the dot renders with no background — invisible.

**Fix:** Add a fallback color and remove the unreachable `info` key from the non-severity map:
```typescript
const inlineColor = !isSev ? ({
  ok:    'var(--ok-fg)',
  error: 'var(--err-fg)',
  warn:  'var(--warn-fg)',
} as Record<string, string>)[status] ?? 'var(--fg-4)' : undefined;
```

---

### WR-04: Sidebar nav items are `<div>` elements — not keyboard-accessible

**File:** `dashboard/src/components/Shell.tsx:58-68`
**Issue:** Each nav item is a `<div onClick=...>` without `role`, `tabIndex`, or `onKeyDown`. Keyboard-only users cannot navigate the sidebar at all. This affects every page in the application.

**Fix:** Either use `<button>` elements (simplest) or add the minimum ARIA attributes:
```tsx
<div
  key={it.id}
  role="button"
  tabIndex={0}
  data-nav={it.id}
  className={`nav-item${active === it.id ? ' active' : ''}`}
  onClick={() => onNav(it.id)}
  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onNav(it.id); } }}
>
```

---

### WR-05: Topbar bell button clears the count on every click even when count is zero — unintended side-effect

**File:** `dashboard/src/components/Shell.tsx:111`
**Issue:** The bell `<button>` always calls `onClearCritHigh` on click, even when `newCritHighCount` is `0`. This is a no-op today but will silently clear any future state that `onClearCritHigh` might manage. The button also has no accessible label — screen readers see only the SVG icon with no text alternative.

**Fix:**
```tsx
<button
  className="btn ghost"
  style={{ padding: 6, position: 'relative' }}
  aria-label={`Notifications${(newCritHighCount ?? 0) > 0 ? ` — ${newCritHighCount} new critical/high` : ''}`}
  onClick={(newCritHighCount ?? 0) > 0 ? onClearCritHigh : undefined}
>
```

---

### WR-06: `executeCommand` in Chat.tsx silently drops the loading spinner when `cmd === 'approve'` or `cmd === 'revoke'`

**File:** `dashboard/src/pages/Chat.tsx:152-165`
**Issue:** When `cmd` is `'approve'` or `'revoke'`, the code adds a loading message at line 144 (`addMsg({ role: 'ai', text: '⏳ Đang xử lý…', loading: true })`), then immediately filters it out at lines 155 and 163 (`setMessages(m => m.filter(msg => !(msg.loading)))`). This is a setstate-race: React batches state updates in concurrent mode, so the filter may run before the prior `addMsg` is committed, leaving the loading message permanently in the list. More importantly, the filter uses `!(msg.loading)` which removes *all* loading messages, not just the one that was just added — if two commands are in-flight simultaneously this would incorrectly remove the wrong message.

**Fix:** Assign a unique ID to each message and remove only that specific message:
```typescript
const loadingId = Date.now();
addMsg({ id: loadingId, role: 'ai', text: '⏳ Đang xử lý…', loading: true });
// ...
setMessages(m => m.filter(msg => msg.id !== loadingId));
```
(Requires adding `id` to the `Message` interface.)

---

### WR-07: `PageVulns` polling in `useEffect` does not cancel the in-flight fetch on cleanup — stale data can overwrite newer state

**File:** `dashboard/src/pages/Vulns.tsx:417-430`
**Issue:** The `setInterval` callback calls `api.findings.list(p).then(setFindings)`. If the component unmounts or `projectFilter` changes while a fetch is in-flight, the `.then(setFindings)` callback will still fire after unmount (or after the filter changed), potentially overwriting the results of the newer fetch. There is no `AbortController` usage and no mounted-guard.

**Fix:**
```typescript
useEffect(() => {
  let mounted = true;
  setLoading(true);
  const params = { limit: 500, ...(projectFilter !== 'all' ? { project_id: projectFilter as number } : {}) };
  api.findings.list(params)
    .then(f => { if (mounted) { setFindings(f); setLoading(false); } })
    .catch(() => { if (mounted) setLoading(false); });

  const id = setInterval(() => {
    api.findings.list(params).then(f => { if (mounted) setFindings(f); }).catch(() => {});
  }, 30_000);

  return () => { mounted = false; clearInterval(id); };
}, [projectFilter]);
```

---

### WR-08: `ToggleRow` in Settings.tsx initializes local state from props but never syncs — `on` prop changes are ignored

**File:** `dashboard/src/pages/Settings.tsx:9-18`
**Issue:** `ToggleRow` stores `on` in local state via `useState(on)`. If the parent ever re-renders with a different `on` value (e.g., after loading settings from the server), the toggle stays at its initial value. Additionally, toggling the switch sends no API call — the state change is purely cosmetic and is lost on navigation. This is silent data loss from the user's perspective.

**Fix (minimal):** If these toggles are purely display-only demo elements with no persistence, add a comment making that explicit and remove the unused `setChecked` state setter. If they should persist, wire up an `onChange` prop and an API call.

---

### WR-09: `ActionDialog` error from `onConfirm` is silently swallowed — user gets no feedback on failure

**File:** `dashboard/src/components/modals/ActionDialog.tsx:49-57`
**Issue:** `handleConfirm` calls `await onConfirm(justification.trim())`. If `onConfirm` throws, the `catch` block only resets `loading` to `false`. The dialog remains open but shows no error message. The user sees the spinner disappear with no indication of what went wrong.

**Fix:** Add an error state to the dialog:
```typescript
const [error, setError] = useState('');

const handleConfirm = async () => {
  if (!isValid || loading) return;
  setLoading(true);
  setError('');
  try {
    await onConfirm(justification.trim());
    onClose();
  } catch (e) {
    setError(String(e));
    setLoading(false);
  }
};

// In JSX, above the button row:
{error && <div style={{ fontSize: 12, color: 'var(--err-fg)', marginTop: 8 }}>{error}</div>}
```

---

## Info

### IN-01: `Badge` component class name has potential double-space when `cls` is empty

**File:** `dashboard/src/components/Badge.tsx:18`
**Issue:** When `variant` is `'neutral'`, `cls` is `''`. The template literal `` `chip${dot ? ' dot' : ''} ${cls}` `` produces `"chip "` or `"chip dot "` (trailing space). `.trim()` catches the trailing space but a double-space in the middle (`"chip  "`) for non-dot neutral badges may still occur. This is cosmetic but produces invalid class lists.

**Fix:**
```typescript
const parts = ['chip', dot ? 'dot' : '', cls].filter(Boolean);
return <span className={parts.join(' ')}>{children}</span>;
```

---

### IN-02: Magic numbers for `MIN_CHARS` validation are duplicated between display and logic

**File:** `dashboard/src/components/modals/ActionDialog.tsx:28-29, 99`
**Issue:** `MIN_CHARS = 20` is defined locally in `handleConfirm`'s containing function. The value itself is fine (it is named), but the validation feedback message at line 99 uses `justification.trim().length` while `isValid` at line 29 also uses `.trim().length`. This is consistent, but the character count shown to the user (`MIN_CHARS - justification.trim().length`) double-trims. If the user types only spaces, `isValid` is false and the message correctly shows the full 20 chars needed — but `.trim()` is called twice needlessly. No bug, but worth noting.

---

### IN-03: `search-box input` in `Shell.tsx` Topbar is `readOnly` — non-functional search placeholder

**File:** `dashboard/src/components/Shell.tsx:108`
**Issue:** The search input renders with `readOnly` attribute and no `onChange` handler. Clicking it and typing does nothing. The `⌘K` hint implies a keyboard shortcut that is also not wired up. This is either dead UI or an unimplemented feature with no TODO comment.

**Fix:** Add a `// TODO: implement global search` comment, or wire up the shortcut handler, or render the element with `disabled` styling so users do not attempt to interact with it.

---

### IN-04: Hardcoded user "Minh Tran" / "MT" avatar in `Shell.tsx` sidebar footer

**File:** `dashboard/src/components/Shell.tsx:72-76`
**Issue:** The sidebar footer displays a hardcoded `"Minh Tran"` name, `"MT"` initials, and `"SAST_CICD · admin"` role. There is no connection to the authenticated user from `Chat.tsx`'s login state. If the auth system is expanded, this will show stale/wrong user info.

**Fix:** Pass the authenticated user info as a prop to `Sidebar`, or source it from a shared auth context.

---

### IN-05: `tokens.css` defines `--ts-xl: 30px` but the type scale comment says "5 stops" — there are actually 6 stops

**File:** `dashboard/src/tokens.css:51-56`
**Issue:** The comment says "5 stops, no in-between values" but the file defines `--ts-xs`, `--ts-sm`, `--ts-base`, `--ts-md`, `--ts-lg`, and `--ts-xl` — six distinct stops. The discrepancy will confuse contributors deciding whether to add a new size token.

**Fix:** Update the comment to "6 stops".

---

_Reviewed: 2026-04-28T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

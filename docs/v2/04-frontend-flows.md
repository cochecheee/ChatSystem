# 04 — Frontend flows

`dashboard/` — React 19 + Vite + TypeScript. SPA, 9 pages, không router lib (state-driven switch trong `App.tsx`).

## 4.1 Routing & shell

**Source**: `dashboard/src/App.tsx`

```
<AuthProvider>
  <ProjectProvider>
    <AppInner>
       Sidebar  Topbar
       <page>          ← switch (active) trong useState<PageId>
       <LoginModal>    ← global, mở khi 401 hoặc click Sign in
    </AppInner>
  </ProjectProvider>
</AuthProvider>
```

`PageId` enum: `overview | pipelines | vulns | sca | runtime | monitor | chat | reports | settings`.

`Sidebar` nhóm 3 groups (Workspace / Assistant / Admin) — định nghĩa trong `components/Shell.tsx:22`.

## 4.2 Context layer

### `AuthContext` (`features/auth/AuthContext.tsx`)

State: `{ user: { username, role } | null, login(username, role), logout() }`.

- `login()` → `POST /api/chat/auth/token` → `setAuthToken()` localStorage → `setUser()`.
- Mount: nếu có token trong localStorage → `GET /api/chat/auth/me` để verify, set user. Fail (401) → clear.
- `logout()` → `setAuthToken(null)` + `setUser(null)`.

### `ProjectContext` (`contexts/ProjectContext.tsx`)

State: `{ projects, activeProjectId, setActiveProjectId, refresh, loading }`.

- Mount: `api.projects.list()` → store.
- `activeProjectId` lưu vào localStorage để giữ qua reload.
- Selector trong Topbar (`ProjectSelector` component): user chọn project → mọi page filter theo `activeProjectId`.
- `useActiveProjectParam()` hook → `{ project_id: activeProjectId }` hoặc `undefined`. Pages dùng trực tiếp pass vào `api.findings.list({ project_id })`.
- Khi auth identity đổi (`user?.username`) → `refreshProjects()` để RBAC-filtered list update tức thì.

## 4.3 API client (`api/client.ts`)

Pattern wrapper:
- `BASE = VITE_API_URL ?? 'http://localhost:8000'` (env-driven).
- `authHeaders()` đọc `_token` global, add `Authorization: Bearer`.
- `get<T>`, `getWithTotal<T>` (đọc thêm `X-Total-Count`), `post<T>` — đều xử lý 401.
- **401 challenge**: `handle401(status)` gọi `_onAuthChallenge` callback. `App.tsx` register callback ở mount → mở `LoginModal`. → bất kỳ fetch nào hit 401 đều tự pop login → 1 chỗ xử lý, không page nào phải tự lo.

`api` object có shape:
```ts
api.findings.{list, listWithTotal, get, explain, triage, aiSummary, gateCount}
api.monitor.{summary, uptime, alerts, ack, ping}
api.projects.{list, listMembers, addMember, removeMember,
              listSuppressions, addSuppression, deleteSuppression,
              create, delete}
api.stats.{overview, latestScan, runs}
api.github.{runs, artifacts, runFindings, reprocessRun}
api.chat.{login, me, command, message, reportUrl}
api.config.{list, get, update, integrations}
api.health()
```

## 4.4 Polling strategy

`POLL_INTERVAL_MS` từ `lib/constants.ts`. Mỗi page dùng `useEffect`:

```tsx
useEffect(() => {
  const fetch = () => api.stats.overview({project_id}).then(setData);
  fetch();
  const id = setInterval(fetch, POLL_INTERVAL_MS);
  return () => clearInterval(id);
}, [activeProjectId]);
```

Khi đổi project, baseline (vd. `critHighRef`) reset để không spam toast "+N new"
spurious khi tenant mới có sẵn count cao hơn (`App.tsx:46`).

## 4.5 Pages overview

| Page | Mục đích | Endpoint chính | Side panels |
|------|----------|----------------|-------------|
| **Overview** | KPI cards, Donut severity, Pipeline status, AI summary card V3.3.B | `/stats/overview`, `/stats/latest-scan`, `/findings/ai-summary` | `OverviewAiSummary` 4-section markdown |
| **Pipelines** | List GitHub workflow runs, click → board cho run đó: severity bar, tool breakdown, top 10, artifacts | `/github/runs`, `/github/runs/{id}/findings`, `/github/runs/{id}/artifacts`, `/github/runs/{id}/reprocess` | Reprocess button cho ai từng chỉnh normalizer |
| **Vulnerabilities** | Split list+detail. Filter severity/tool/status. AI panel (Gemini analysis + diff viewer). Modal approve/revoke | `/findings` (paginated), `/findings/{id}/explain` | `AiTriageModal` (V3.1 Tier 3) bulk classify |
| **SCA** | Dependencies subset (Trivy + DepCheck) — cùng API nhưng `category=deps` | `/findings?category=deps` | — |
| **Runtime (DAST)** | ZAP findings — `category=dast` | `/findings?category=dast` | — |
| **Monitor** | Uptime checks + alerts với chart | `/monitor/summary`, `/monitor/uptime`, `/monitor/alerts`, `/monitor/ack` | Manual `POST /monitor/ping` button |
| **Chat** | ChatOps: slash command + free-form. Lịch sử local-only (không persist) | `/api/chat/command`, `/api/chat/message`, `/api/chat/report` | Approve/Revoke dialog (`modals/`) |
| **Reports** | Generate HTML download, list previous reports | `/api/chat/report` (HTML response) | — |
| **Settings** | 3 tabs: Tools, Gates, AI. Edit `app_config` keys. Per-project member + suppression management | `/config/{key}`, `/projects/{id}/members`, `/projects/{id}/suppressions` | `ProjectMembers`, `ProjectSuppressions` |

## 4.6 Custom hooks

- `useOverviewStats()` — `features/findings/useStats.ts`. Wrap polling cho overview.
- `useRuns()` — `features/pipelines/useRuns.ts`. Wrap polling cho GitHub runs.
- `usePolling()` — `hooks/usePolling.ts`. Generic interval hook (chưa dùng rộng).

## 4.7 Auth flow (UI)

```
User click "Sign in" trong Topbar
    │
    ▼
LoginModal mở (controlled từ App.tsx loginOpen)
    │
    ▼
Chọn role: developer | security_lead | admin
Nhập username (free text, demo only)
    │
    ▼
auth.login(username, role) →
   POST /api/chat/auth/token { username, role }
    │
    ▼
Backend trả { access_token } với memberships snapshot
    │
    ▼
client.setAuthToken(token) → localStorage
AuthContext.setUser({ username, role })
    │
    ▼
ProjectContext.refreshProjects() → re-fetch /projects
    (RBAC filtering kick in nếu RBAC_PER_PROJECT=true)
    │
    ▼
Modal close
```

401 flow:
```
Bất kỳ fetch nào trả 401
    → handle401() trong client
    → _onAuthChallenge() (callback đã register từ App)
    → setLoginOpen(true)
    → User re-login
```

## 4.8 Tại sao thiết kế FE thế này (quick rationale)

| Choice | Lý do |
|--------|------|
| Không react-router | 9 page tabular, không deep linking thật. State-switch đủ. (Có lúc cần `?vuln=42` deep link — handle bằng `initialId` prop pass xuống Vulns) |
| Không state lib (Redux/Zustand) | 2 context đủ. Mỗi page tự quản state riêng — không cross-page sharing nặng. |
| Polling thay vì WebSocket/SSE | Free Render không idle-friendly cho long-lived; polling 5-15s đủ cho thesis demo. |
| Inline SVG icon | Tránh sprite/font dep. ~60 icon trong `Icon.tsx`. |
| Manual TypeScript interface (không zod / openapi-codegen) | Schema BE relative stable; tay viết nhanh hơn maintain codegen pipeline ở thesis size. |
| `setInterval` thay vì `useSWR`/`useQuery` | Đơn giản; không cần cache stale-while-revalidate. |

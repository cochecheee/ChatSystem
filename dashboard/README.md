# Dashboard — chat-system frontend

React 19 + TypeScript + Vite SPA. Hiển thị Findings, Pipelines, AI summary, ChatOps cho MCP gateway.

## Yêu cầu

- Node.js ≥ 20
- npm ≥ 10 (đi kèm Node 20)
- Backend `mcp/` đang chạy ở `http://localhost:8000` (hoặc set `VITE_API_URL` khác)

## Setup

```bash
cd dashboard
npm install

# Cấu hình URL backend. File .env.local đã có VITE_API_URL=http://localhost:8000 cho dev.
# Đổi nếu backend chạy port khác hoặc deploy remote.
cp .env.local.example .env.local 2>/dev/null || true

npm run dev   # http://localhost:5173
```

Login lần đầu: dùng tài khoản demo trong `mcp/docs/setup.md` (account `admin` hoặc seed user của project).

## Scripts

| Lệnh | Mục đích |
|---|---|
| `npm run dev` | Vite dev server với HMR (port 5173) |
| `npm run build` | TypeScript check + Vite production build → `dist/` |
| `npm run preview` | Serve `dist/` để smoke test trước khi deploy |
| `npm run lint` | ESLint check toàn bộ `src/` |
| `npm run format` | Prettier format tất cả file |
| `npm run format:check` | Prettier check, không sửa (CI dùng cái này) |
| `npm run test:e2e` | Playwright chạy headless |
| `npm run test:e2e:ui` | Playwright UI mode để debug spec |

CI (`.github/workflows/ci.yml`) chạy `lint`, `format:check`, `build` trên mỗi PR.

## Cấu trúc thư mục

```
src/
├── api/           # Fetch wrapper + endpoint client (client.ts)
├── components/    # Component dùng chung (Badge, Icon, OverviewAiSummary, ...)
├── contexts/      # React Context (AuthContext, ProjectContext)
├── features/      # Domain feature (auth, findings, pipelines, config)
├── hooks/         # Custom hook (usePolling, useResizableSplit)
├── lib/           # Constants
├── pages/         # Top-level page component (Overview, Vulns, Pipelines, ...)
├── types/         # Shared type
└── App.tsx        # Router (manual switch-case) + provider compose

tests/e2e/         # Playwright spec
```

## Convention

- File component: `PascalCase.tsx`. Hook/util: `camelCase.ts`.
- Single quote, semicolon, 2-space indent, trailing comma kiểu `es5`. Prettier config trong `.prettierrc.json`.
- Export named, không dùng default export trừ khi cần lazy import.
- Type tách qua `import type { ... } from '...'`.
- Tránh `any` — nếu phải dùng, đánh comment giải thích.
- Inline style hạn chế; dùng CSS class trong `App.css` / `index.css` / `tokens.css`.

## State management

- **Global state**: Context API (`AuthContext`, `ProjectContext`) với `localStorage` persist.
- **Server state**: fetch thủ công qua `api/client.ts` + polling bằng `setInterval` trong page. TanStack Query là follow-up.
- **Form state**: `useState` local. Chưa có form library.

## Routing

Manual `switch(pageId)` trong `App.tsx`. Mỗi page là 1 enum `PageId`. Chuyển sang React Router là backlog item.

## Debug

- Vite dev console + React DevTools.
- Network 401 → check `localStorage.getItem('auth_token')` còn không, refresh page nếu hết hạn.
- Polling không trigger → check `ProjectContext.activeProjectId` đã set chưa.
- Playwright fail flaky → chạy `npm run test:e2e:ui` để xem từng step.

## Đóng góp

Xem [CONTRIBUTING.md](../CONTRIBUTING.md) ở root repo.

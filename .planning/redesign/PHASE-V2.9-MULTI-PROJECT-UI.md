# Phase V2.9 — Multi-Project UI

**Branch**: `ft/imp-fe` (continue)
**Goal**: User chọn project trên dashboard → mọi page lọc findings/stats/runs theo project đó.
**Driver**: V2.8 backend đã multi-tenant nhưng FE flat — không demo được "1 mcp serve N inheritor".

## Backend changes (B)

| # | Việc | File | Test |
|---|---|---|---|
| B1 | `GET /findings?project_id=<id>` filter via Finding→Artifact→Run→Project | `mcp/src/api/findings.py`, `repositories/finding_repo.py` | 2 case |
| B2 | `GET /stats/overview?project_id=` filter | `mcp/src/api/stats.py` | 1 case |
| B3 | `GET /github/runs?project_id=` filter | `mcp/src/api/github_runs.py` | 1 case |
| B4 | `GET /projects` đã có — verify trả về list w/ decrypted credentials hidden (mask token) | `mcp/src/api/artifacts.py` | 1 case |

Default `project_id=None` → trả về all (backward compat).

## Frontend changes (F)

| # | Việc | File |
|---|---|---|
| F1 | `ProjectContext` provider — fetch `/projects`, cache, expose `{activeProjectId, setActiveProjectId, projects[]}` | `dashboard/src/contexts/ProjectContext.tsx` |
| F2 | `<ProjectSelector />` dropdown trong header (`All projects` + per-project) | `dashboard/src/components/ProjectSelector.tsx` |
| F3 | Hooks `useFindings/useStats/useRuns` đọc `activeProjectId` từ context, append `?project_id=` | hooks hiện hữu |
| F4 | Trang `Projects.tsx` — list + nút "Add project" mở modal wizard 9-field | `dashboard/src/pages/Projects.tsx` |
| F5 | Route `/projects` thêm vào `App.tsx` + sidebar nav | `dashboard/src/App.tsx` |

## Steps (sequential, verify each)

| # | Việc | Pytest delta | Status |
|---|---|---|---|
| 1 | B1 — findings filter | 242 → 244 | TODO |
| 2 | B2 — stats filter | 244 → 245 | TODO |
| 3 | B3 — runs filter | 245 → 246 | TODO |
| 4 | B4 — projects list mask token | 246 → 247 | TODO |
| 5 | F1+F2 — ProjectContext + Selector | — | TODO |
| 6 | F3 — hooks param | — | TODO |
| 7 | F4+F5 — Projects page + wizard | — | TODO |
| 8 | E2E smoke: tạo project ALOUTE qua wizard, chọn, verify findings filter | — | TODO |

## Verify

- Pytest: 247/247
- Vite dev: chọn dropdown "ALOUTE" → Overview/Vulns chỉ hiện finding của ALOUTE
- Network tab: requests có `?project_id=`
- "All projects" → behavior cũ

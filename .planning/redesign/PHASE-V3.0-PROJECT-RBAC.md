# Phase V3.0 — Per-Project RBAC

**Branch**: `ft/imp-fe` (continue)
**Goal**: User chỉ thấy/thao tác project mà mình là member; role per-project quyết định approve/revoke/explain quyền.
**Driver**: V2.9 cho phép multi-project view; cần phân quyền để demo "Security Lead của project A không can thiệp project B".

## Design — Option A (chốt)

Role enum 4-mức per `(user, project)`:
| Role | Permission |
|---|---|
| `owner` | Tất cả + invite/remove member + edit project credentials |
| `security_lead` | Approve/revoke finding, trigger scan, explain |
| `developer` | View finding, explain (read LLM), không approve |
| `viewer` | Read-only mọi resource |

Global role `admin` (đã có) = super-admin, bypass per-project check.

## Schema

```sql
CREATE TABLE project_members (
    user_id     INTEGER NOT NULL,
    project_id  INTEGER NOT NULL,
    role        VARCHAR(20) NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, project_id)
);
CREATE INDEX ix_project_members_project ON project_members(project_id);
```

Auto-migrate ở `lifespan` (đã có pattern V2.6/V2.8).

## Backend changes (B)

| # | Việc | File |
|---|---|---|
| B1 | Entity `ProjectMember` + relationship `User.memberships` / `Project.members` | `mcp/src/models/entities.py` |
| B2 | `ProjectMemberRepository.{list_for_user, get_role, add, remove}` | `mcp/src/repositories/project_member_repo.py` (mới) |
| B3 | Login (`POST /api/chat/auth/token`) thêm `memberships` vào JWT claim | `mcp/src/services/auth.py` |
| B4 | Middleware `require_project_access(project_id, min_role)` — decorator/dep injection | `mcp/src/core/auth_deps.py` |
| B5 | Wire mọi endpoint nhận `project_id`: `/findings?project_id=`, `/findings/{id}/approve`, `/findings/{id}/revoke`, `/findings/{id}/explain`, `/projects/{id}` | api routes |
| B6 | Endpoint quản lý members: `GET/POST/DELETE /projects/{id}/members` (chỉ owner) | `mcp/src/api/artifacts.py` |
| B7 | `GET /projects` filter — user không phải admin chỉ thấy project có membership | `mcp/src/api/artifacts.py` |
| B8 | Kill-switch `RBAC_PER_PROJECT=true` default false → khi false, mọi authenticated user xem hết (V2.9 behavior) | `mcp/src/core/config.py` |
| B9 | Seed: user đầu tiên login + owner mọi project hiện hữu (one-time migration) | `mcp/src/db.py` |

## Frontend changes (F)

| # | Việc | File |
|---|---|---|
| F1 | `ProjectSelector` ẩn project không có membership | `dashboard/src/components/ProjectSelector.tsx` |
| F2 | Trang `ProjectSettings.tsx` — tab Members: list, invite-form (username + role), remove button | `dashboard/src/pages/ProjectSettings.tsx` (mới) |
| F3 | UI disable nút Approve/Revoke nếu role < security_lead | tooltip + disabled state |
| F4 | Error toast 403 → "You don't have permission for this project" | `dashboard/src/lib/api.ts` |

## Steps

| # | Việc | Pytest delta | Status |
|---|---|---|---|
| 1 | B1 + B2 — entity + repo | +3 | TODO |
| 2 | B3 — JWT memberships claim | +2 | TODO |
| 3 | B4 + B8 — middleware + kill-switch | +2 | TODO |
| 4 | B5 — wire endpoints (per-project gate) | +4 | TODO |
| 5 | B6 + B7 — member CRUD + project list filter | +3 | TODO |
| 6 | B9 — seed migration | +1 | TODO |
| 7 | F1 + F2 + F3 + F4 | — | TODO |
| 8 | RBAC matrix test (3 user × 2 project × 4 role) | +12 | TODO |
| 9 | E2E smoke: 2 user, 2 project, verify cross-project denial | — | TODO |

**Target pytest**: 247 → 274.

## Verify

- Pytest matrix all green
- Smoke:
  - userA owner project1 → approve finding project1 ✅
  - userA viewer project2 → approve finding project2 ❌ 403
  - userB (no membership) → `/projects` trả về `[]`
  - global admin → mọi action ✅
- UI: dropdown ẩn project không có membership; approve button disabled cho viewer

## Backward compat

- `RBAC_PER_PROJECT=false` (default) → bypass, V2.9 behavior
- Global `admin` role → super-admin xuyên RBAC
- Existing users without membership + flag on → auto-seed owner first project (one-time migration)

# 05 — API reference

Bảng đầy đủ các endpoint, kèm auth, RBAC, side-effect. Cập nhật theo source thực tế (`mcp/src/api/*.py`).

Auth column:
- **none**: không cần header (anonymous OK)
- **JWT**: Bearer JWT từ `/api/chat/auth/token`
- **CI_API_KEY**: header `X-API-Key`
- **CI_WEBHOOK_TOKEN**: Bearer = `CI_WEBHOOK_TOKEN`
- **read-gate**: `require_read_access` — JWT trừ khi `ANONYMOUS_READ_ENABLED=true`

## 5.1 Health & meta

| Method | Path | Auth | Mô tả |
|--------|------|------|------|
| GET | `/` | none | Banner + version |
| GET | `/health` | none | Liveness probe |
| GET | `/health/flags` | none | Feature-flag state (boolean + raw env) cho ops |

## 5.2 Projects (multi-tenant)

| Method | Path | Auth | RBAC | Mô tả |
|--------|------|------|------|------|
| GET | `/projects` | read-gate | filtered theo memberships nếu RBAC on | List projects |
| POST | `/projects` | none (TODO: hardening) | — | Tạo project, full credentials |
| DELETE | `/projects/{id}` | none (TODO) | — | Xoá + cascade artifacts/findings |
| GET | `/projects/{id}/integration` | none | — | YAML/curl snippet để gắn webhook vào repo target |
| GET | `/projects/{id}/members` | JWT optional | nếu RBAC on, caller phải có role trên project | List members |
| POST | `/projects/{id}/members` | JWT | owner-only (hoặc admin) | Add/update member |
| DELETE | `/projects/{id}/members/{username}` | JWT | owner-only | Remove member |
| GET | `/projects/{id}/suppressions` | none | — | List rules (?include_expired=true) |
| POST | `/projects/{id}/suppressions` | JWT | security_lead+ | Tạo rule |
| DELETE | `/projects/{id}/suppressions/{rule_id}` | JWT | security_lead+ | Xoá rule |

## 5.3 Findings

| Method | Path | Auth | RBAC | Mô tả |
|--------|------|------|------|------|
| GET | `/findings` | read-gate | scoped theo memberships | Filter: `project_id`, `severity`, `tool`, `status`, `category` (sast/deps/dast), `q`, `run_id`, `exclude_revoked`, `skip`/`limit`. Header `X-Total-Count`. |
| GET | `/findings/{id}` | read-gate | — | Detail |
| POST | `/findings/{id}/explain` | JWT | developer+ trên project | AI analysis qua Gemini. Cache vào `ai_analysis` JSON. |
| GET | `/findings/ai-summary` | read-gate | scoped | V3.3.B Gemini risk briefing 4-section. Cache 10 phút, `force_refresh=true` để bust. |
| POST | `/findings/triage` | JWT | security_lead+ trên project | V3.1 Tier 3 batch AI triage, REVOKE FP confidence ≥ threshold. `dry_run=true` để preview. |
| GET | `/findings/gate-count` | JWT **hoặc** CI_WEBHOOK_TOKEN | — | V3.1 Tier 4 Security Gate. Counts {critical, high, medium, low} loại REVOKED. |

## 5.4 GitHub Actions browser

| Method | Path | Auth | Mô tả |
|--------|------|------|------|
| GET | `/github/runs` | read-gate | `?branch=`, `?status=`, `?project_id=` (per-project credentials). |
| GET | `/github/runs/{run_id}/artifacts` | read-gate | List artifacts của 1 run |
| GET | `/github/runs/{run_id}/findings` | read-gate | Findings đã normalize cho run đó |
| POST | `/github/runs/{run_id}/reprocess` | none (TODO) | Wipe + re-ingest. Schedule background task. 202. |

## 5.5 Ingest

| Method | Path | Auth | Mô tả |
|--------|------|------|------|
| POST | `/artifacts/process` | CI_API_KEY (nếu set) | CI gửi 1 artifact id để process. 202 + db_artifact_id. |
| POST | `/webhook/pipeline-complete` | CI_WEBHOOK_TOKEN (nếu set) | CI báo run xong. Multi-tenant lookup theo `repository` field. 202. |

## 5.6 Chat / ChatOps

| Method | Path | Auth | Mô tả |
|--------|------|------|------|
| POST | `/api/chat/auth/token` | none | Demo login → JWT (memberships snapshot embedded) |
| GET | `/api/chat/auth/me` | JWT | Validate token + return user info |
| POST | `/api/chat/command` | JWT | 11 lệnh, role check theo `COMMAND_ROLES` map |
| POST | `/api/chat/message` | JWT | Free-form Gemini chat + suggested slash command |
| GET | `/api/chat/report` | JWT | HTML download, role `developer+` |

Lệnh cho `/api/chat/command`:

| Cmd | Args | Role | Action |
|-----|------|------|--------|
| `/explain` | `finding_id` | developer+ | Gọi `LLMAnalysisService` |
| `/fix` | `finding_id` | developer+ | Reuse explain |
| `/scan` | — | security_lead+ | `dispatch_workflow('ci.yml')` |
| `/rerun` | `run_id` | security_lead+ | `rerun_workflow(run_id)` |
| `/approve` | `finding_id`, `justification` (≥20) | security_lead+ | Set APPROVED + audit |
| `/revoke` | `finding_id`, `justification` (≥20) | security_lead+ | Set REVOKED + audit |
| `/report` | — | developer+ | HTML generate |
| `/status` | — | developer+ | Latest workflow run summary |
| `/results` | `[run_id]` | developer+ | Severity breakdown + top 5 |
| `/help` | — | all | List 11 lệnh |
| `/feedback` | `[finding_id]`, `feedback_text` (≥5) | all | Persist CommandFeedback row |

## 5.7 Stats

| Method | Path | Auth | Mô tả |
|--------|------|------|------|
| GET | `/stats/overview` | read-gate | KPI tổng + by_severity/status/tool. `?project_id=`. |
| GET | `/stats/latest-scan` | read-gate | Scope về run mới nhất. `?project_id=`. |
| GET | `/stats/runs` | read-gate | Pass rate + by_day. `?days=` (default 30). |

## 5.8 Config

| Method | Path | Auth | Mô tả |
|--------|------|------|------|
| GET | `/config` | none | All config keys |
| GET | `/config/{key}` | none | 1 key (`sast_tools`, `gates`, `ai`) |
| PUT | `/config/{key}` | JWT admin | Update — admin only |
| GET | `/config/integrations` | none | Status GitHub/Gemini/CI ingest. KHÔNG trả secret value. |

## 5.9 Monitor

| Method | Path | Auth | Mô tả |
|--------|------|------|------|
| GET | `/monitor/uptime` | none | `?project_id=`, `?hours=` (max 168) |
| GET | `/monitor/summary` | none | Aggregate uptime % per target |
| GET | `/monitor/alerts` | none | `?kind=`, `?only_open=` |
| POST | `/monitor/alerts/{id}/ack` | none | Ack alert |
| POST | `/monitor/ping` | none | Manual cycle trigger (demo) |

## 5.10 Test-only (TEST_MODE=1)

| Method | Path | Mô tả |
|--------|------|------|
| POST | `/test/reset` | Wipe findings/artifacts/projects |
| POST | `/test/inject-finding` | Insert finding cho E2E |

## 5.11 Error response shape

FastAPI default:
```json
{ "detail": "Finding #42 không tìm thấy." }
```

Status codes thực tế dùng:
- `200`: OK
- `201`: Created (POST /projects, POST /members, POST /suppressions)
- `202`: Accepted (background task scheduled)
- `204`: No Content (DELETE, ACK)
- `400`: Validation logic (severity INFO không cần approve, role không hợp lệ)
- `401`: Missing/invalid JWT
- `403`: Auth OK nhưng thiếu role / membership / api key sai
- `404`: Resource không tồn tại
- `409`: State conflict (đã APPROVED, đã REVOKED)
- `422`: Pydantic validation / business rule (justification < 20)
- `502`: GitHub API upstream lỗi
- `503`: Gemini unavailable

## 5.12 Cách thêm endpoint mới (template)

1. Tạo router trong `api/<feature>.py` hoặc thêm vào existing
2. Auth dependencies:
   - read-side: `_: User | None = Depends(require_read_access)`
   - write-side: `current: User = Depends(get_current_user)`
   - project-scoped: `_: User = Depends(require_project_access(min_role="..."))`
3. Repository pattern:
   ```python
   repo = FindingRepository(session)
   results = await repo.list_with_filters(...)
   ```
4. RBAC scoping:
   ```python
   scope_ids = allowed_project_ids(user)
   if scope_ids is not None and project_id not in scope_ids:
       raise HTTPException(403, "Not in your memberships")
   ```
5. Register vào `main.py` qua `app.include_router(...)`.
6. Thêm vào `dashboard/src/api/client.ts` (TypeScript interface).
7. Test: `pytest tests/test_<feature>.py`.

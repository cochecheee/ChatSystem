# Phase V2.8 — Multi-Tenant Runtime

**Branch**: `verify-work` (continue từ V2.7) hoặc nhánh mới `feat/multi-tenant`
**Mục tiêu**: Một mcp instance serve N inheritor (sample-python + ALOUTE + …) thay vì hard-code 1 repo qua env
**Driver**: User đã ship ALOUTE workflow nhưng mcp single-tenant → CodeQL Java/SpotBugs/DepCheck của ALOUTE chưa bao giờ ingest đúng. Cần multi-tenant để defense full chain
**Ngày bắt đầu**: 2026-05-15

## Bản chất technical debt

`Project` entity có 9 column credentials (V2.1.2 scaffolding) nhưng runtime đọc từ env:
- `GitHubPoller.__init__` → `settings.GITHUB_TOKEN/OWNER/REPO`
- `SecurityProcessor.process_run(project_id, run_id)` → `self.github_client` (env-bound)
- `LLMAnalysisService.analyze_finding` → `GeminiClient()` (env-bound, singleton)
- `/webhook/pipeline-complete` → `ProjectRepository.get_or_create_by_github_url(name=f"{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}")` — luôn create cùng 1 project
- `POST /projects` → chỉ persist `name + github_url`, các field khác drop silent

## Pre-flight (BẮT BUỘC TRƯỚC RUNTIME CHANGE)

| # | Việc | Effort | Status |
|---|---|---|---|
| P1 | Snapshot DB hiện tại — mcp.db local + Render Postgres backup | 10' | TODO |
| P2 | Audit webhook callers gửi `repository` field | 30' | TODO |
| P3 | Backward-compat fallback path khi không tìm project | 1h | TODO |
| P4 | Feature flag `MULTI_TENANT_ENABLED` default false | 30' | TODO |
| P5 | Test fixture parametrize / auto-seed default project | 2-3h | TODO |
| P6 | Fernet encrypt token/api_key (defer to Phase A A1) | 1h | TODO |
| P7 | Fix `ProjectRepository.create()` persist 9 field | 30' | TODO |

## Phase A — Foundation (sau pre-flight)

| Step | Việc | Verify |
|---|---|---|
| A1 | `core/secrets.py` Fernet helper + `FERNET_KEY` env | 5 unit test |
| A2 | Migration backfill existing Project → encrypted | pytest assert |
| A3 | `ProjectRepository.create()` persist 9 field (đã làm ở P7) | (verify) |
| A4 | `ProjectOut` schema KHÔNG expose secret raw | manual curl |
| A5 | UI Settings page form 9 field + "configured" badges | playwright |

## Phase B — Runtime switch

| Step | Việc | Verify |
|---|---|---|
| B1 | Webhook handler route theo `repository` field | 2 test (new+legacy) |
| B2 | `SecurityProcessor` luôn use per-project GitHub client | existing test pass |
| B3 | `GitHubPoller` iterate active projects với semaphore=3 | mock 2 projects |
| B4 | `LLMAnalysisService` per-project gemini_api_key + cache | 2-project test |
| B5 | Monitor targets per-project (optional) | defer v0.3.x |

## Phase C — Multi-inheritor verify

| Step | Việc |
|---|---|
| C1 | Tạo 2 Project rows (sample-python + SAST_CICD) qua API |
| C2 | Trigger CI cả 2 đồng thời |
| C3 | Filter findings theo project_id → đếm đúng |
| C4 | Switch MULTI_TENANT_ENABLED=true ở Render |

## Phase D — UI polish (optional)

D1 Project selector mỗi page · D2 Add-project wizard · D3 Audit log per-project context

## Risk matrix

| Risk | Mitigation |
|---|---|
| Webhook không có repository field | Fallback path P3 + log warning |
| 200 test break vì assume single project | P5 fixture refactor + flag off in test env |
| Migration encrypt lỗi → mất data | P1 snapshot |
| Fernet key rotate → mất decrypt | Document procedure, key gen note trong SECRETS.txt |
| Webhook race condition tạo duplicate | Idempotent từ V2.4 65ce7b0 — verify lại |
| Gemini quota N×60req/min | Document limits.md |

## Tracking

| Item | Status | Commit | Note |
|---|---|---|---|
| P1 snapshot | DONE | file backup | mcp.db.20260515-223558.bak + Render projects/findings JSON |
| P2 audit webhook | DONE | in-place note | sast-action notify + ALOUTE notify.py đều gửi `repository` field |
| P3 fallback path | DONE | 93ab28d | webhook lookup → fallback env |
| P4 feature flag | DONE | 93ab28d | `MULTI_TENANT_ENABLED` default False, `FERNET_KEY` empty |
| P5 test coverage | DONE | 93ab28d | 3 routing + 1 persist 9 field, 228/228 |
| P6 Fernet | DONE | 77e4126 | (moved up — done with A1) |
| P7 persist 9 field | DONE | 93ab28d | `model_dump()` instead of name+url only |
| Phase A1 Fernet encrypt | DONE | 77e4126 | 5 unit + live smoke at rest |
| Phase A2 migration | DEFER | — | chỉ cần khi prod có row plaintext + key rotate |
| Phase B1 webhook routing | DONE | 93ab28d | (with P3) |
| Phase B2 SecurityProcessor | DONE | 27d07cd | per-project github client + 3 test |
| Phase B3 GitHubPoller | DONE | 095e614 | asyncio.gather + semaphore + 3 test |
| Phase B4 LLMAnalysisService | DONE | 27d07cd | per-project gemini key, cache, 3 test |
| Phase C verify | DONE | local smoke script | 2 project routing + decrypt verified |
| Phase D UI polish | TODO | — | optional v0.3 |

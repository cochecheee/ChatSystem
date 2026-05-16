# Quality Audit — V3.2 hardening

**Date**: 2026-05-16
**Scope**: Fix illogical behavior + dead code + UX confusion. **No new features.**
**Audit method**: grep across mcp/src + dashboard/src for known smells, trace flows.

## Findings (severity-ordered)

### BUG — must fix

**BUG-1 — Webhook không update `last_processed_run_id`**
- File: `mcp/src/services/processor.py::process_run`
- Symptom: Live verify thấy ALOUTE `last_processed_run_id=None` dù đã ingest 184 findings qua webhook
- Root cause: poller path update field (poller.py:130) nhưng `process_run` không update — webhook flow bị bypass
- Fix: cuối `process_run`, update `project.last_processed_run_id` nếu `github_run_id > current`
- Impact: UI hiển thị đúng "last scanned run", `/projects` API source of truth
- Risk: thấp (chỉ thêm UPDATE)

**BUG-2 — Hardcoded sample data trên Overview**
- File: `dashboard/src/pages/Overview.tsx:17-25`
- Smell: `TREND_28D`, `FIXED_28D`, `SPARKS` là arrays cứng → AreaTrend + Sparkline render fake data
- Defense risk: hội đồng phản biện hỏi "data này từ đâu?" → không trả lời được
- Fix: hoặc (A) thay bằng data từ `/stats/runs?days=28` thật, (B) bỏ panel + sparkline đi
- Đề xuất: (B) bỏ — vì stats/runs trả `by_day` aggregate đủ thông tin, không cần 2 trend chart
- Risk: thấp (xóa UI)

**BUG-3 — `require_project_access` dep DEFINED nhưng KHÔNG WIRED**
- File: `mcp/src/core/auth.py:68` định nghĩa, không endpoint nào dùng
- Symptom: RBAC_PER_PROJECT=true nhưng approve/revoke/explain finding KHÔNG check membership
- Root cause: V3.0 implement dep + tests nhưng quên wire vào finding action routes
- Endpoints cần wire (qua chain Finding → Artifact → project_id):
  - `POST /findings/{id}/explain` (LLM analyze)
  - `POST /findings/{id}/approve` (chat command path)
  - `POST /findings/{id}/revoke`
- Fix: thêm `Depends(require_project_access(min_role="security_lead"))` hoặc lookup project_id từ finding rồi check thủ công
- Tricky: dep factory resolve project_id từ path/query — finding_id không phải project_id, cần lookup
- Risk: trung — đụng auth path, cần thêm test

**BUG-4 — Per-artifact failure crash whole run**
- File: `mcp/src/services/processor.py::process_run` (lines 116-148)
- Smell: `process_artifact` raise exception → bubbles up, vòng for dừng giữa chừng → các artifact sau không process
- Real risk: 1 artifact lỗi (zip corrupt, timeout) → toàn run drop
- Fix: bọc `await self.process_artifact(...)` trong try/except, log error, continue
- Risk: thấp

**BUG-5 — Webhook re-fire duplicate findings**
- File: `mcp/src/services/processor.py::process_run` lines 124-148
- Logic hiện: nếu artifact tồn tại + status="processed" → skip. Nhưng nếu status="pending" hoặc "failed" → re-process → `_run` add findings mới mà KHÔNG delete cũ trước → tích lũy duplicate
- Repro: trong session vừa rồi, ta fire webhook 3-4 lần do Render restart — may mắn artifact status=processed nên skip. Nhưng nếu lần 1 fail mid → lần 2 sẽ duplicate.
- Fix: trước khi process pending/failed artifact, delete its existing findings
- Risk: thấp

### SMELL — should fix

**SMELL-6 — `FindingOut` thiếu `project_id`**
- File: `mcp/src/models/schemas.py:79-96`
- Smell: API trả Finding không kèm project_id → UI không biết finding thuộc project nào → khi user filter mixed cũ tưởng "data lẫn lộn"
- Fix: add `project_id: int` computed property trên Finding ORM (qua artifact.project_id), expose qua FindingOut
- Cần eager-load Artifact relationship hoặc lookup riêng → choose: add to Finding via @property + eager-load via repo
- Risk: thấp

**SMELL-7 — Stale `B2 (future)` comment**
- File: `mcp/src/api/artifacts.py:566`
- Comment nói "truyền project để processor.process_run dùng per-project client. Hiện B2 chưa wire" — nhưng B2 đã wire ở V2.8 rồi
- Fix: xóa comment lạc hậu
- Risk: 0

**SMELL-8 — Pydantic v2 deprecation warnings**
- File: `mcp/tests/test_rbac_v3.py:137`
- `setattr(mock_settings, attr, getattr(real, attr))` → ăn `model_fields` / `model_computed_fields` qua instance → deprecation
- Fix: dùng `type(real).model_fields` thay vì instance access
- Risk: 0

### Defer — bigger refactor, skip cho lần này

- **Retroactive suppression**: add rule không apply ngược findings cũ (cần nút "Apply now" — feature mới, defer)
- **JWT refresh-token flow**: stale memberships khi admin kick (architectural change, defer)
- **Fernet key versioning**: rotation bị break (defer)

---

## Plan execute

Sequential, verify each:

| # | Fix | Effort | Pytest delta |
|---|---|---|---|
| 1 | BUG-1: webhook update last_processed_run_id | 15' | +1 |
| 2 | BUG-4: isolate per-artifact errors | 15' | +1 |
| 3 | BUG-5: cleanup pending/failed before re-ingest | 20' | +1 |
| 4 | BUG-3: wire RBAC on approve/revoke/explain | 45' | +3 |
| 5 | SMELL-6: project_id trên FindingOut | 20' | +1 |
| 6 | SMELL-7+8: dead comment + pydantic warnings | 10' | 0 |
| 7 | BUG-2: bỏ hardcoded Overview trend | 15' | 0 (FE) |

**Target pytest**: 269 → 276 (+7).
**Risk profile**: tất cả non-breaking — flags off vẫn behave như trước, flags on enforce thêm.

## Smoke test checklist

After all fixes:
- [ ] Fire webhook → ALOUTE `last_processed_run_id` updates
- [ ] Re-fire webhook same run_id → no duplicate findings
- [ ] viewer-demo user tries /findings/{id}/approve → 403 (with RBAC on)
- [ ] FindingOut JSON includes `project_id`
- [ ] Overview page: no fake trend chart
- [ ] Pytest all green
- [ ] Dashboard TS clean

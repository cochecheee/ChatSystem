# Phase 6 Context: Advanced Dashboard Features & Final Integration

## Phase Goal
Implement các tính năng nâng cao và E2E testing cho toàn bộ hệ thống.

## Command Assignment (Final)

### Phase 5 handles (simple read-only):
- `/status` → `GET /api/pipeline/status` — trạng thái pipeline gần nhất
- `/results` → `GET /api/findings` — danh sách findings

### Phase 6 handles (complex actions):
| Command | Backend Logic | Role Required |
|---------|--------------|---------------|
| `/explain [finding_id]` | Gọi LLMAnalysisService | developer+ |
| `/fix [finding_id]` | Gọi LLMAnalysisService | developer+ |
| `/scan` | Dispatch GitHub Actions workflow mới | security_lead+ |
| `/rerun [run_id]` | Re-run failed workflow | security_lead+ |
| `/approve [finding_id]` | Update finding status → APPROVED + lưu audit | security_lead+ |
| `/revoke [finding_id]` | Update finding status → REVOKED + lưu audit | security_lead+ |
| `/report` | Generate HTML report từ findings | developer+ |

## Decisions

### Backend (FastAPI)
- D-01: Unified `/api/chat/command` endpoint parse và route tất cả 7 commands.
- D-02: JWT role check **trước** khi route — trả 403 nếu không đủ quyền.
- D-03: `/approve` và `/revoke` lưu đầy đủ audit trail:
  - `status`: PENDING → APPROVED hoặc REVOKED
  - `justification` / `revoke_justification`: min 20 chars
  - `approved_by` / `revoked_by`: username từ JWT
  - `approved_at` / `revoked_at`: timestamp
- D-04: `/report` generate HTML report server-side, trả về file download.
- D-05: Không approve finding đã APPROVED; không revoke finding đã REVOKED hoặc INFO severity.
- D-06: `/scan` và `/rerun` gọi `GitHubClient.dispatch_workflow()` từ Phase 2.

### Frontend (React)
- D-07: `sonner` cho tất cả toast notifications.
- D-08: `ApprovalDialog` và `RevokeDialog` — cùng component base, khác title/color.
- D-09: `/report` trả về HTML blob → mở tab mới hoặc download.
- D-10: Chat Panel hiển thị status message khi command đang xử lý ("⏳ Đang phân tích...").

### Testing (Playwright)
- D-11: Full-stack E2E — FastAPI (TEST_MODE=1, SQLite :memory:) + Vite dev server.
- D-12: Chromium only.
- D-13: LLM bypass qua `TEST_MODE=1`, GitHub API mock qua `page.route()`.
- D-14: Test cases phải cover: unauthorized access, approve/revoke flow, report download.

## Requirements Reference
- REQ-04-03: Slash commands /explain, /fix, /approve, /rerun, /scan, /revoke, /report.
- REQ-06-01: Toast notifications.
- REQ-06-02: Approval workflow với justification.
- REQ-06-03: E2E system verification.

# REDUNDANCY — Cắt gì, giữ gì, gộp gì

> Quyết định danh sách cắt cụ thể. Mỗi mục có lý do + risk khi cắt.

---

## 1. Cắt thẳng tay (Frontend — 2566 LOC)

| File | LOC | Lý do cắt | Risk |
|---|---|---|---|
| `dashboard/src/pages/Dast.tsx` | 930 | Mock data, không có DAST backend, OWASP ZAP/Nikto chưa wire | Mất "show breadth" — chấp nhận |
| ~~`dashboard/src/pages/Sca.tsx`~~ | ~~417~~ | ~~Trùng Dependency-Check trong Vulns~~ | **CORRECTION 2026-05-08**: SCA KHÔNG redundant — Vulns hardcode `category=sast` (loại tool ∈ DEPS_TOOLS). Tao đã rebuild Sca.tsx với REAL data (commit 8161184), không phải mock. |
| `dashboard/src/pages/Secrets.tsx` | 469 | Mock; không integrate TruffleHog/Gitleaks | Mất theatre — chấp nhận |
| `dashboard/src/pages/PRBot.tsx` | 386 | Mâu thuẫn human-in-the-loop principle | Không |
| `dashboard/src/pages/Governance.tsx` | 305 | Pure decoration | Không |
| `dashboard/src/pages/Repos.tsx` | 59 | Có thể gộp vào Settings | Không, gộp lại |
| `dashboard/src/data/mockData.ts` | ? | Còn không cần sau khi cắt 6 page trên | Không |

**Action**: xóa 6 file pages + mockData.ts, xóa import + route trong `App.tsx`, dọn sidebar trong `Shell.tsx` (group "Workspace" còn Overview/Pipelines/Vulns; bỏ "Assistant" PR Bot, bỏ "Admin" Governance/Repos).

**Giảm**: 2566/5494 = **47% page code**, kéo theo bundle nhỏ + load nhanh + test E2E nhẹ.

---

## 2. Đánh giá lại (có thể gộp / refactor)

| Item | Hiện trạng | Đề xuất | Lý do |
|---|---|---|---|
| `services/config_service.py` (77 LOC) vs `core/config.py` | 2 file config song song | Gộp về `core/config.py` | Tránh 2 source of truth |
| `api/config.py` (77 LOC) | Endpoint cấu hình runtime | Giữ nhưng simplify nếu chỉ phục vụ 1 repo (sau refactor multi-project nếu vẫn giữ — full) | Tùy hướng đa-project |
| `Reports.tsx` (238 LOC) | HTML report download | Giữ nhưng simplify — chỉ 1 button "Export run #N report" | Hiện tại quá nhiều state |
| `Settings.tsx` (455 LOC) | Page rộng | Giữ nhưng cắt section liên quan repos (gộp Repos vào đây) | |

---

## 3. Backend — không cắt nhưng phải SỬA

| File | Vấn đề | Action |
|---|---|---|
| `services/processor.py` L21-33 | Hardcode artifact names | Đưa vào `Project.artifact_patterns` (DB column JSON) hoặc `.env` |
| `core/config.py` | `GITHUB_OWNER`, `GITHUB_REPO` singleton | Convert thành per-`Project` (đã có `Project` entity sẵn) |
| `services/poller.py` | Poll 1 repo singleton | Loop tất cả `Project` |
| `services/github_client.py` | Constructor lấy default từ settings | Bắt buộc inject `owner/repo` từ Project |
| `services/llm/prompts.py` | Có thể hardcode style/locale | Cho phép override per-project (nếu tham vọng) |

**Lưu ý**: nếu chốt option **A. Docker Compose template** (1 instance = 1 project), KHÔNG cần multi-project ở DB layer — chỉ cần extract hardcoded values ra `.env`. Tiết kiệm 1.5 ngày.

---

## 4. Tests — review theo scope mới

- `mcp/tests/` (162 tests) — sau khi cắt mock pages, **backend tests không bị ảnh hưởng** (chỉ test core service).
- `dashboard/tests/e2e/` — kiểm tra spec file:
  - `chatops.spec.ts` — giữ
  - `approval.spec.ts` — giữ
  - `report.spec.ts` — giữ
  - `polling.spec.ts` — giữ
  - Bất kỳ spec nào test mock pages → xóa

---

## 5. Documentation cần dọn

- `.planning/phase-2..6/research/RESEARCH.md` — đã marked deleted trong git status (mày đang xóa rồi, OK).
- `images/image*.png` (13 ảnh) — giữ những ảnh demo Overview/Vulns/Chat/Pipelines. Cắt ảnh về DAST/SCA/Secrets/PRBot/Governance.
- `README.md` — phần "Tính năng" hiện liệt kê đủ thứ; sau khi cắt, viết lại theo scope thật.
- `run.txt` — replace bằng `Makefile` hoặc `scripts/dev.ps1` (xem PLAN).

---

## 6. Tổng kết "cắt"

```
Frontend:  −2566 LOC pages + mockData.ts + Sidebar groups  → −47%
Backend:   0 LOC cắt, ~50 LOC extract config thành dynamic  → 0%
Docs:      cắt 5 phase docs ảo + 6 mock-feature ảnh         → −60% planning bloat
Tests:     loại spec liên quan mock                         → ~−10%
```

**Sản phẩm sau khi cắt**:
- 6 page real (Overview, Pipelines, Vulns, Chat, Reports, Settings)
- Backend gọn, có thể package
- Demo runs end-to-end trên ALOUTE_Spring_Thymeleaf_RCE
- Có tài liệu integration cho repo khác

→ Tiếp theo: xem `REUSABILITY.md` quyết hướng đóng gói.

<!-- Cảm ơn đã đóng góp! Điền các phần dưới — mục nào không áp dụng thì xoá. -->

## Tóm tắt

<!-- 1-3 câu mô tả thay đổi này làm gì. Tập trung vào WHY hơn WHAT. -->

## Loại thay đổi

- [ ] `feat` — feature mới
- [ ] `fix` — sửa bug
- [ ] `refactor` — đổi code, không đổi behavior
- [ ] `docs` — chỉ doc
- [ ] `chore` — build/CI/tooling
- [ ] `test` — thêm/sửa test

## Linked issue

Closes #

## Checklist trước khi request review

- [ ] Commit message theo Conventional Commits (`feat:`, `fix:`, `chore:` ...)
- [ ] Đã chạy `ruff check . && ruff format --check .` (backend) hoặc `npm run lint && npm run format:check` (frontend)
- [ ] Test pass local: `pytest -q` (mcp) hoặc `npm run build` (dashboard)
- [ ] Thay đổi UI: đã kiểm tra trên browser, không lỗi console mới
- [ ] Thay đổi BE: đã thêm/cập nhật test cho hành vi mới
- [ ] Không commit secret (token, password, API key) — `.env` vẫn nằm trong `.gitignore`

## Cách verify (cho reviewer)

<!-- Bước cụ thể để reviewer chạy thử. Ví dụ: "Mở Vulns tab, click Revoke, xác nhận badge flip về REV." -->

## Note thêm

<!-- Trade-off, alternative đã consider, follow-up biết trước. -->

# PLAN — Triển khai 1 tuần (2026-05-08 → 2026-05-15)

> Lịch ngày, mục tiêu cuối tuần là demo end-to-end trên ALOUTE + repo Python demo phụ + sản phẩm đóng gói cấp 2.5.

**Hôm nay**: thứ Sáu 2026-05-08. Deadline: thứ Sáu 2026-05-15 (cứng).

**Giả định**: làm full-time, ~6-7h thực sự code/ngày.

**Scope chốt theo OPEN-QUESTIONS đã trả lời**:
- Q1 = B (multi-tenant nhẹ — extract config per-Project, không full RBAC tách)
- Q2 = CÓ demo Python repo thứ 2 (lồng vào Day 5)
- Q3 = Cấp 2.5 (Docker Hub push + GitHub release v0.1.0 + minimal composite Action; KHÔNG Helm, KHÔNG full TS Action)
- Q11 = **CẮT báo cáo IEEE khỏi scope tuần này** — viết sau 2026-05-15
- Q12 = không meeting GVHD giữa tuần
- Secrets: đã có hết

---

## Định nghĩa "DONE" cho tuần này

1. ✅ Cắt sạch 6 mock pages, dashboard chỉ còn 6 page real, build pass.
2. ✅ Backend chạy multi-`Project` (đọc owner/repo + artifact patterns từ DB hoặc config file thay vì `.env` cứng).
3. ✅ Đóng gói thành `docker compose up -d` chạy được trên máy mới.
4. ✅ Demo end-to-end trên ALOUTE_Spring_Thymeleaf_RCE: push code → CI → SAST findings xuất hiện trong dashboard → /explain ra remediation → /approve có audit trail.
5. ✅ Tài liệu: `docs/integration.md` + `docs/webhook-schema.md` + `docs/adapter-guide.md`.
6. ✅ README viết lại theo scope mới.
7. ✅ Slide / bài thuyết trình có khung (không cần hoàn thiện slide nhưng phải có outline).

---

## Day-by-day

### Day 1 — Thứ Sáu 2026-05-08 (hôm nay) — Cleanup + foundation
**Mục tiêu**: cắt sạch mock + tách config khỏi hardcode.

| Block | Task | Output |
|---|---|---|
| 2h | Xóa 6 mock pages (Dast, Sca, Secrets, PRBot, Governance, Repos) + `mockData.ts` + import trong `App.tsx`, `Shell.tsx` | Build dashboard pass, sidebar gọn |
| 1h | Xóa E2E spec liên quan, dọn `playwright.config.ts` nếu cần | `npm run test:e2e` pass |
| 2h | Refactor `processor.py` — `_SECURITY_ARTIFACT_NAMES` thành config-driven (đọc từ `config/profiles/*.yml`) | `processor.py` không hardcode |
| 1h | Tạo `config/profiles/github-actions-default.yml` cho ALOUTE pipeline | File chuẩn |
| **Cuối ngày** | Commit `chore: cut mock pages, externalize artifact config` | 1 commit sạch |

### Day 2 — Thứ Bảy 2026-05-09 — Multi-project ở backend
**Mục tiêu**: 1 instance phục vụ nhiều `Project`. Mỗi project có own GitHub creds + artifact profile.

| Block | Task |
|---|---|
| 2h | DB migration: thêm `Project.github_token_secret`, `Project.artifact_profile_name`, `Project.gemini_api_key_secret` (encrypted hoặc env-ref) |
| 2h | Refactor `GitHubClient` constructor — nhận `Project` thay vì đọc `settings` |
| 1h | Refactor `poller.py` — loop mọi `Project` thay vì 1 |
| 1h | Update API `/api/projects` POST — accept full config |
| **Test** | Tạo 2 project test, verify poller pull đúng từng repo |

### Day 3 — Chủ Nhật 2026-05-10 — Webhook schema + AI guardrails verify
**Mục tiêu**: chốt contract `/webhook/pipeline-complete` + đảm bảo guardrails work.

| Block | Task |
|---|---|
| 2h | Viết `docs/webhook-schema.md` — JSON shape, header auth, retry policy |
| 1h | Verify `core/guardrails.py` scrub PII/secret/injection — chạy lại unit tests, fix nếu fail |
| 2h | Implement `/api/projects/{id}/test-webhook` — endpoint cho team test integration |
| 1h | Cleanup `services/llm/prompts.py` — đảm bảo prompt không leak project-specific data |

### Day 4 — Thứ Hai 2026-05-11 — Docker packaging + đẩy Docker Hub
**Mục tiêu**: `docker compose up -d` chạy được + image public trên Docker Hub.

| Block | Task |
|---|---|
| 2h | Viết `Dockerfile` cho `mcp/` (multi-stage, Python 3.13 slim) |
| 1h | Viết `Dockerfile` cho `dashboard/` (build + nginx serve static) |
| 1.5h | Viết `docker-compose.yml` (mcp + dashboard + volume cho `mcp.db`) + `docker-compose.example.yml` + `.env.example` |
| 1h | Test fresh-clone + `docker compose up` trên WSL clean |
| 1h | **Cấp 2.5**: Tạo workflow `.github/workflows/release.yml` cho chat-system — build & push `cochecheee/sast-chat-mcp:latest` + `cochecheee/sast-chat-dashboard:latest` lên Docker Hub khi tag |

### Day 5 — Thứ Ba 2026-05-12 — Demo wire-up ALOUTE + Python repo thứ 2
**Mục tiêu**: 2 project chạy song song, chứng minh reuse thật.

| Block | Task |
|---|---|
| 0.5h | Deploy chat-system local + cloudflared tunnel → public URL |
| 0.5h | Tạo Project ALOUTE trong dashboard + update ALOUTE secrets `MCP_GATEWAY_URL` + `MCP_WEBHOOK_TOKEN` |
| 1h | Trigger CI ALOUTE → watch findings + test 7 ChatOps commands |
| 2h | **Demo phụ**: tạo repo `sast-chat-demo-python` (private hoặc public) — 1 file `vulnerable.py` có SQLi/RCE intentional, viết `.github/workflows/sast.yml` chạy Bandit + Semgrep, profile `python-default.yml` |
| 1.5h | Tạo Project Python trong dashboard + trigger CI repo Python → verify findings cũng vào cùng dashboard |
| 0.5h | Capture screenshot 2 project chạy parallel cho slide |
| 1h | Buffer fix bug |

### Day 6 — Thứ Tư 2026-05-13 — Tài liệu + adapter guide
**Mục tiêu**: project khác đọc docs là onboard được.

| Block | Task |
|---|---|
| 2h | Viết `docs/integration.md` — quickstart 30 phút |
| 2h | Viết `docs/adapter-guide.md` — cách thêm Normalizer cho tool mới (vd: Bandit Python) |
| 1h | Tạo example profile `config/profiles/python-bandit.yml` (chứng minh extensible) |
| 1h | Viết lại `README.md` — gỡ feature ảo, ghi đúng scope |
| 1h | Cleanup commit history nếu cần (squash WIP commits) |

### Day 7 — Thứ Năm 2026-05-14 — Composite Action + GitHub Release + polish
**Mục tiêu**: cấp 2.5 hoàn thiện + slide có khung + screencast.

| Block | Task |
|---|---|
| 2h | **Cấp 2.5 — minimal composite Action**: tạo `action.yml` ở repo gốc (composite action) — input: `dashboard-url`, `dashboard-token`, `run-metadata-path` → step `curl POST` đến webhook. Test trên ALOUTE (replace step `Dispatch to MCP Gateway` bằng `uses: cochecheee/chat-system@v0.1.0`) |
| 1h | **Cấp 2.5 — GitHub release v0.1.0**: tag, viết CHANGELOG.md, draft release note với 3 ảnh demo |
| 1.5h | UI polish — empty states, error toast, loading skeleton 6 page real |
| 1h | Slide outline: problem → architecture → demo flow → reusability story (2 project ALOUTE+Python) → roadmap V2 |
| 0.5h | Record screencast demo backup |
| 1h | Buffer |

### Day 8 — Thứ Sáu 2026-05-15 — Final polish + rehearse
- Slide finalize.
- Rehearse demo 2-3 lần.
- Push final tag + release.
- Buffer cho bug last-minute.

> Lưu ý: báo cáo IEEE (Q11) đã CẮT khỏi scope tuần này — viết riêng từ tuần sau.

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Multi-project refactor đụng 162 unit test | Cao | Migrate test fixtures cùng lúc; chạy `pytest -q` sau mỗi commit |
| Gemini API rate-limit khi demo | Trung bình | Pre-cache 5-10 finding analysis trong DB trước demo |
| ALOUTE CI fail vì SonarCloud token | Trung bình | Skip Gate 2 trong demo, chỉ chạy Gate 1 + notify |
| Cloudflare tunnel / ngrok rớt khi demo | Thấp | Có screencast backup |
| Sentinel design dependency vỡ khi cắt mock | Thấp | Test build sau mỗi xóa file |
| Mock data còn linkage trong Vulns/Overview | Trung bình | Grep `mockData` toàn repo trước commit |

---

## Cắt scope khẩn cấp (nếu chậm progress)

Theo thứ tự ưu tiên cắt từ trên xuống nếu thiếu thời gian:

1. **CẮT trước**: Adapter guide + python-bandit example (Day 6) → giảm 3h.
2. **CẮT tiếp**: Multi-project ở backend (Day 2) → fallback: 1 instance = 1 project (single-tenant), vẫn deploy được, vẫn demo end-to-end OK.
3. **CẮT cuối**: Docker compose example cho project khác (Day 4 cuối ngày) → fallback: chỉ docker-compose chính cho ALOUTE.

**KHÔNG bao giờ cắt**:
- Cắt mock pages (Day 1) — phải làm vì thesis.
- Demo end-to-end ALOUTE (Day 5) — không có cái này thì không có gì để bảo vệ.
- README + integration.md cơ bản (Day 6) — để hội đồng đọc.

---

## Daily checklist tóm tắt

```
[ ] Day 1 (Fri 05-08): 6 mock pages cut + artifact profile externalized
[ ] Day 2 (Sat 05-09): Multi-project backend (multi-tenant nhẹ)
[ ] Day 3 (Sun 05-10): Webhook schema doc + guardrails verified
[ ] Day 4 (Mon 05-11): Docker compose + Docker Hub release workflow
[ ] Day 5 (Tue 05-12): ALOUTE demo + Python repo demo (2 project parallel)
[ ] Day 6 (Wed 05-13): docs/integration.md + docs/adapter-guide.md
[ ] Day 7 (Thu 05-14): Composite Action + v0.1.0 release + slide outline + screencast
[ ] Day 8 (Fri 05-15): Final polish + rehearse demo
```

---

## Sau 1 tuần (roadmap V2 — không phải scope thesis)

- **Option B GitHub Action wrapper** — biến chat-system thành plug-and-play CLI/Action.
- **Multi-tenant UI** — login + project switcher.
- **GitLab / Bitbucket adapter** — không phụ thuộc GitHub Actions.
- **DAST integration thật** (OWASP ZAP) — thay cho mock đã cắt.

→ Còn câu hỏi mở: xem `OPEN-QUESTIONS.md`.

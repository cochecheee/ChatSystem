# PROGRESS — Trạng thái thực tế

> Cập nhật mỗi cuối ngày code. Đối chiếu với `PLAN-1WEEK.md`.

**Last updated**: 2026-05-08 (cuối Day 1)

---

## Tổng quan

```
[✅] Day 1 (Fri 05-08): Cleanup + foundation — DONE + extras
[  ] Day 2 (Sat 05-09): Multi-tenant backend
[  ] Day 3 (Sun 05-10): Webhook schema doc + guardrails verified
[  ] Day 4 (Mon 05-11): Docker compose + Docker Hub release workflow
[  ] Day 5 (Tue 05-12): ALOUTE demo + Python repo demo (2 project parallel)
[  ] Day 6 (Wed 05-13): docs/integration.md + docs/adapter-guide.md
[  ] Day 7 (Thu 05-14): Composite Action + v0.1.0 release + slide + screencast
[  ] Day 8 (Fri 05-15): Final polish + rehearse demo
```

---

## Day 1 — Fri 2026-05-08 — DONE (vượt scope)

### Đúng kế hoạch
- ✅ Cắt 6 mock pages (Dast, Sca, Secrets, PRBot, Governance, Repos) + `mockData.ts`
- ✅ App.tsx + Shell.tsx pruned — sidebar 12 → 7 page
- ✅ Tách hardcoded `_SECURITY_ARTIFACT_NAMES` → `mcp/config/profiles/github-actions-default.yml` + `core/profiles.py` loader
- ✅ Build dashboard pass (`tsc -b && vite build` clean)
- ✅ Backend pytest 200/200 pass
- ✅ Commit `chore(redesign): cut mock pages, externalize artifact profile` (`426424d`)

### Extras phát hiện ngoài kế hoạch
1. **SCA tab thực ra cần REAL data** — `REDUNDANCY.md` ban đầu sai (đã correct ở `4f5f2a7`). Lý do: Vulns hardcode `category=sast` loại trừ DEPS_TOOLS → deps cần page riêng.
   - ✅ Build lại Sca.tsx với data thật (`8161184`)
   - ✅ Group findings theo `(package, current_version)` + recommend max fix version + dedup CVE per package (`00bf366`)
   - Lý do: Trivy container scan flood ~4000 CVE noise, group lại còn ~50-100 dependencies actionable

2. **DB cleanup tooling**
   - ✅ `mcp/scripts/cleanup_db.py` — xóa artifact failed orphan (đã chạy: 286 → 117 artifacts, 8280 findings preserved)
   - ✅ `mcp/scripts/reset_db.py` — wipe sạch dev DB (chưa chạy `--apply`, chờ user)

3. **Stats per-category để badge khớp tab**
   - ✅ Backend trả `sast_open` / `deps_open` / `sast_critical_high` / `deps_critical_high` (`35ca0eb`, `cdb7fae`)
   - ✅ Cuối cùng quyết định bỏ hẳn count badge khỏi sidebar (`553f89d`) — số nào cũng không phản ánh đúng "actionable" theo cảm nhận user

4. **ALOUTE workflow fixes** (cross-repo, Day 5 work làm sớm)
   - ✅ Bump retention-days SAST artifact 1 → 30 (toàn bộ 6 tools) — chống 410 Gone khi poller pull
   - ✅ Speed up dependency-check: timeout 20→40m, cache theo tháng thay vì tuần, `nvd.api.validForHours` 24→720, disable ossindex/node analyzers
   - ✅ Bust dep-check cache `v2` để fix H2 schema VARCHAR(1000) bug (CVE reference URL > 1500 chars)

5. **Repo housekeeping**
   - ✅ Xóa 78 file `.planning/` cũ (~18k LOC stale planning docs)
   - ✅ `.gitignore` chặn `dashboard/test-results/`, `dashboard/mcp.db`, `.claude/`
   - ✅ Bundle WIP code có sẵn (Charts/Icon polish, features/auth/findings/pipelines, repositories/, tests config/stats/pagination/delete) thành 1 commit gọn

### Đo đạc
| Metric | Trước Day 1 | Sau Day 1 |
|---|---|---|
| Pages dashboard | 12 (6 real + 6 mock) | 7 real (thêm SCA) |
| LOC pages | ~5494 | ~3700 |
| Bundle JS gzip | n/a (chưa đo) | 86.76 KB |
| Backend pytest | 162 (theo README) | 200/200 |
| DB artifacts | 286 | 117 |
| ALOUTE retention SAST | 1 ngày | 30 ngày |

### Commits (chat-system, branch `ft/imp-fe`)
```
4a1bd6c chore: bring in pre-redesign WIP + harden .gitignore
cc5c94b chore(planning): remove superseded phase docs
553f89d refactor(sidebar): drop count badges next to nav items
cdb7fae feat(stats): badge counts critical+high so SCA tab matches sidebar
35ca0eb feat(stats): per-category open counts so sidebar badges match tabs
61042f8 chore: add reset_db script + clarify SCA severity floor label
00bf366 feat(sca): group CVEs by dependency, recommend max fix version
4f5f2a7 docs(redesign): correct SCA redundancy claim
8161184 feat(sca): restore Dependencies tab with real backend data
426424d chore(redesign): cut mock pages, externalize artifact profile
```

### Commits (ALOUTE, branch `main`, đã push)
```
856928e ci: bust dep-check cache (v2) to drop old H2 schema
6cffa8f ci: speed up dependency-check, finish retention bumps
b04ae9c ci: bump SAST artifact retention to 30 days
```

### Còn treo cuối Day 1
- ⏳ User cần chạy `python -m scripts.reset_db --apply` để dọn 8280 Trivy CVE cũ
- ⏳ Verify CI ALOUTE chạy thành công với cache `depcheck-v2` (đợi user report)

---

## Day 2 — Sat 2026-05-09 — Multi-tenant backend

**Mục tiêu**: 1 instance phục vụ N project, mỗi project có own GitHub creds + Gemini key + artifact profile.

Kế hoạch theo PLAN-1WEEK.md không đổi. Bắt đầu khi user "go Day 2".

---

## Câu hỏi mở còn lại

Tham chiếu `OPEN-QUESTIONS.md` — đã trả lời hết Q1-Q12 cuối Day 1. Không câu hỏi mở mới.

---

## Risk hiện tại

| Risk | Likelihood | Status | Mitigation |
|---|---|---|---|
| CI ALOUTE vẫn fail dep-check | Trung bình | ⏳ chờ verify | Fallback: `if: false` skip job |
| Multi-tenant refactor đụng 200 tests Day 2 | Trung bình | mới | Migrate fixtures cùng commit |
| Gemini API quota khi demo | Thấp | mới | Pre-cache 5-10 finding analysis |
| Cloudflared/ngrok rớt khi demo | Thấp | mới | Có screencast backup |

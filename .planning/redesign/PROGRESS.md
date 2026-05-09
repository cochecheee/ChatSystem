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

## Day 2 — Sat 2026-05-09 — REVISED: ALOUTE end-to-end + multi-tenant scaffolding

**Plan revision (2026-05-08 evening)**: User decided "trước tiên thực hiện trên ALOUTE thôi, sau khi đóng gói hết mới test tích hợp được trên nhiều project khác nhau". Day 2 multi-tenant runtime is deferred until after packaging.

### Done (cuối Day 1, lan vào Day 2 sớm)
- ✅ Project entity expanded với 9 multi-tenant columns (defaults backward-compat)
  - `github_owner`, `github_repo`, `github_token`, `gemini_api_key`, `gemini_model`, `artifact_profile`, `polling_workflow_name`, `polling_branch`, `active`
- ✅ `mcp/scripts/migrate_v2.py` — idempotent ALTER TABLE + backfill row đầu tiên từ .env
- ✅ ProjectRepository.create accepts `**fields`, thêm `update()`, `list_active()`
- ✅ `GitHubClient.for_project(project)` classmethod — sẵn để dùng khi multi-tenant runtime kích hoạt
- ✅ `ProjectCreate`/`ProjectUpdate`/`ProjectOut` schemas full multi-tenant fields, secrets không expose qua API (chỉ `has_*` boolean)
- ✅ Poller giữ single-tenant flow — backfill credentials cho Project mới khi tạo từ settings
- ✅ Backend pytest 200/200 pass

### Day 2-3 còn lại (revised scope)
- ✅ ALOUTE end-to-end: migrate_v2 chạy trên DB thật, backfill 9 cột, idempotent verified, live API trả full multi-tenant fields với `has_*` boolean
- ✅ Webhook schema doc (`docs/webhook-schema.md`) — endpoint, header, body, response codes, CI snippet, manual test curl
- ✅ Guardrails verify — 24/24 tests pass, doc `docs/guardrails.md` với 2-layer architecture (Scrubbing + Injection prevention)
- ✅ Endpoint mới `GET /projects/{id}/integration` — trả webhook URL + tên secrets + YAML step + curl test sẵn sàng copy-paste

### Multi-tenant runtime — deferred to Day 6+
- Refactor poller `_poll()` thành loop projects (đã có sẵn implementation, đang revert)
- API endpoints scope per-project
- Multi-tenant test suite

---

## Day 4 — Mon 2026-05-11 — Docker packaging — ✅ DONE (chưa test live)

### Files
- `mcp/Dockerfile` — Python 3.13-slim multi-stage (builder + runtime), non-root `app` user, healthcheck `/health`, mount `/data` cho SQLite
- `mcp/.dockerignore` — strip venv/cache/db
- `dashboard/Dockerfile` — node:20-alpine build → nginx:1.27-alpine serve, healthcheck wget /
- `dashboard/nginx.conf` — single-origin SPA + proxy backend prefixes (`/health`, `/findings`, `/projects`, `/artifacts`, `/github`, `/webhook`, `/api`, `/stats`, `/config`, `/docs`, `/openapi.json`)
- `dashboard/.dockerignore` — strip node_modules/dist/test-results
- `docker-compose.yml` — build từ source, mcp:8000 + dashboard:80→host:5173, named volume `mcp_data`
- `docker-compose.example.yml` — pull `cochecheee/sast-chat-mcp:latest` + `cochecheee/sast-chat-dashboard:latest` từ Docker Hub, không build
- `.env.example` — full env shape ở repo root
- `.github/workflows/release.yml` — build matrix (mcp + dashboard) + push Docker Hub khi tag v*, có gha cache, support manual dispatch

### Còn treo
- ⏳ Local build test — Docker Desktop chưa chạy ở máy user. User tự `docker compose up --build` để verify
- ⏳ Push tag v0.1.0 (chờ Day 7) → workflow release.yml sẽ chạy lần đầu

### Lý do dùng same-origin nginx proxy
- Demo URL chỉ 1 (port 5173 / hostname) — onboard team mới đơn giản
- Tránh CORS — FE build với `VITE_API_URL=""` → relative URLs
- Swagger UI vẫn truy cập được qua `http://host/docs`

---

## Day 5 — Tue 2026-05-12 — ALOUTE demo prep — ✅ DONE (code/docs phần)

User scope: tao làm code/docs, user tự chạy demo (trigger CI, expose ngrok, click UI).

### Files
- `docs/demo-script.md` — bài demo 12-15 phút, 8 phần (Overview → /scan → Pipelines → Vulns + AI → /approve → Dependencies → free-form chat → /report) với expected output từng step
- `docs/preflight-checklist.md` — 9 nhóm check trước demo (env, DB, CI, tunnel, BE/FE, auth, pre-cache AI, browser, backup)
- `docs/troubleshooting.md` — 11 failure mode + fix trong 1-2 phút (dashboard blank, /explain 500, ngrok URL đổi, SCA loading…)
- `mcp/scripts/smoke_test.py` — script tự động kiểm 7 endpoint trước demo (`python -m scripts.smoke_test`)

### Verify
- Smoke script chạy OK khi backend up; logic verify khi backend down (connection refused per check)
- Đã verify code path 7 ChatOps commands ở `command_service.py` — `/explain`, `/fix`, `/scan`, `/rerun`, `/approve`, `/revoke`, `/report` đều validate input + audit trail đầy đủ

### Còn treo (user side)
- Chạy CI ALOUTE mới + verify findings vào dashboard (cache v2 đã pass theo user)
- Set ngrok URL cố định ở `MCP_GATEWAY_URL` GitHub Secret
- Pre-cache 5-10 finding `/explain` trước demo
- Record screencast `docs/demo-recording.mp4` (Day 7)

### Sang Day 6 (docs/integration.md + adapter-guide) khi user OK

---

## Day 6 — Wed 2026-05-13 — DEFERRED

User skipped Day 6 (docs/integration.md + adapter-guide.md), ưu tiên Day 7 trước. Day 6 sẽ làm sau release v0.1.0 nếu còn thời gian.

---

## Day 7 — Thu 2026-05-14 — Composite Action + release prep — ✅ DONE

### Files
- `action.yml` (repo root) — composite GitHub Action, 1-dòng `uses: cochecheee/chat-system@v0.1.0` thay cho bespoke notify step. Inputs: `dashboard-url`, `dashboard-token`, `pipeline-status`, `fail-on-error`, `timeout-seconds`. Outputs: `http-status`, `accepted`. Tolerates gateway downtime mặc định (không fail CI).
- `CHANGELOG.md` — full v0.1.0 entry theo Keep a Changelog format. Added/Changed/Removed/Security/Known limitations.
- `docs/release-notes-v0.1.0.md` — markdown cho GitHub release page, có quickstart curl + composite Action sample + roadmap V2.
- `docs/slide-outline.md` — 12 slide skeleton cho buổi defense ~20 phút, 8-section live demo flow ăn 10', Q&A predicted với canned answers.

### Còn treo (user side)
- Push tag `v0.1.0` để trigger release.yml workflow → push image lên Docker Hub
- Test composite Action trên ALOUTE workflow (replace bespoke notify step bằng `uses:`)
- Record screencast demo backup
- UI polish — empty states/error toast (deferred, không critical cho thesis)
- Convert slide outline → PowerPoint/Canva với screenshot thật

---

## Day 8 — Fri 2026-05-15 — Final polish (user-led)

User chạy demo + rehearse. Code/docs đã ready từ Day 1-7.

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

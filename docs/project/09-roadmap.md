# 09 — Roadmap

## V2 sub-phase order (chốt 2026-05-09, đang execute)

```
✅ V2.1.1  Refactor monolithic action → composite + reusable workflow
✅ V2.1.2  Python sample (Flask vulnerable)
✅ V2.1.3  Test infra (lint + actions-testing.md)
✅ V2.1.4  Repo split (sast-action + sample-python) + Render deploy
✅ V2.1.5  Fix ingest profile + CORS production
✅ V2.2    CD: build image + push Docker Hub + Render deploy hook
✅ V2.3    Runtime DAST (OWASP ZAP baseline) + Runtime tab
✅ V2.4    Monitor (uptime + alert + email + Sentry hook) + Monitor tab
🔄 V2.5    Dashboard Static Site (Blueprint pushed — chờ Render Sync)  ← USER ACTION
🔄 V2.6    Postgres persistence + Monitor→Uptime rename (chờ Render Sync)
✅ V2.7    Docx alignment — polling 15s, 4 commands, 4-layer guardrail
            docs, Security Gate, CodeQL wire, Anthropic MCP server thật
🏁 Tag v0.2.0 sau khi V2.5/V2.6/V2.7 verify
```

---

## V2.2 — CD pipeline ✅ DONE (sast-action side)

**Goal**: Inheritor pass CI → tự deploy lên Render staging.

### Done
- [x] Composite `actions/build-image/`: Docker login + buildx + Trivy image scan + push 2 tags (`<sha>` + `latest`)
- [x] Composite `actions/deploy-staging/`: POST Render Deploy Hook (đơn giản hơn API key)
- [x] Extend `sast-ci.yml`: `cd:` job chạy sau `sast:`, 4 input + 3 secret mới
- [x] Update sample-python `security.yml`: bật `deploy: true`
- [x] Docs: 04-deploy.md, 05-reusable-workflow.md, 07-history.md

### Deferred (sẽ làm khi cần)
- [ ] `Deployment` entity ở mcp DB
- [ ] `POST /webhook/deployment` route
- [ ] Dashboard "Deployed" badge

→ V2.2 đang prove được end-to-end qua CI logs + Docker Hub + Render dashboard. mcp side là nice-to-have, không block V2.3.

---

## V2.3 — Runtime DAST + CVE re-scan (~4 ngày)

**Goal**: Sau khi staging up, chạy OWASP ZAP scan + daily Trivy re-scan CVE database mới.

### Tasks
- [ ] Add composite `actions/run-dast/`
  - OWASP ZAP baseline scan (5 phút)
  - Input: `target_url` (từ V2.2 staging_url)
  - Output: `zap-report.json`
- [ ] Add `ZapNormalizer` ở mcp services
  - Parse ZAP JSON → Finding với `category="dast"`
- [ ] Add scheduled workflow ở sast-action `daily-cve.yml`:
  - Cron: `0 2 * * *` (2 AM UTC)
  - Re-run Trivy + Safety/npm-audit against latest CVE database
  - Diff với previous run → notify nếu có CVE mới
- [ ] Dashboard: tab "Runtime" hiện finding category=dast
- [ ] Test: sample-python deploy → ZAP scan → finding mới ở Runtime tab

---

## V2.4 — Monitor + alert (~3 ngày)

**Goal**: Khi production có lỗi/down → alert qua email + Sentry.

### Tasks
- [ ] Add `Alert` + `UptimeCheck` entities
- [ ] Add `mcp/services/smtp_service.py`
  - SMTP Gmail App Password
  - Template HTML email cho alert types
- [ ] Add Sentry SDK integration
  - `sentry_sdk.init()` với DSN từ env
  - Auto capture exception
- [ ] Add scheduled uptime check (5 phút interval)
  - Ping inheritor staging URL
  - Insert UptimeCheck row
  - Send email nếu down > 2 lần liên tiếp
- [ ] Add composite `actions/notify-monitor/` 
  - Inheritor gọi cuối pipeline → notify monitor health
- [ ] Dashboard: tab "Monitor" hiện uptime chart + alert history
- [ ] Test: stop staging → email alert sau 10 phút

### New env vars
- `SENTRY_DSN`
- `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`, `EMAIL_TO`

---

## V2.5 — Deploy dashboard (~2 ngày)

**Goal**: Dashboard React production-deployed, không cần dev local.

### Tasks
- [ ] Add second service vào `render.yaml`:
  ```yaml
  - type: web
    name: dashboard
    runtime: docker
    plan: free
    dockerfilePath: ./dashboard/Dockerfile
    dockerContext: ./dashboard
    envVars:
      - key: VITE_API_URL
        value: https://mcp-l958.onrender.com
  ```
- [ ] Or: Static Site (recommend nếu CORS configured đúng):
  ```yaml
  - type: web
    name: dashboard
    runtime: static
    buildCommand: npm install && npm run build
    publishPath: ./dashboard/dist
    envVars:
      - key: VITE_API_URL
        value: https://mcp-l958.onrender.com
  ```
- [ ] Update mcp `CORS_ORIGINS` → add dashboard URL
- [ ] Test: open dashboard URL → fetch from mcp → render data

### Resolved decision
- User ban đầu chọn B1 (2 Web Service nginx) vì hiểu nhầm Static Site không gọi được API
- Đã clarify SPA gọi API qua CORS được → Static Site có thể chọn lại
- B1 vẫn OK, chỉ tốn 1 free Web Service slot

---

## V2.7 — Docx báo cáo tiến độ alignment ✅ DONE

**Trigger**: Audit phát hiện gap giữa code và `Nhom04_BaoCaoTienDo1_fixed_1.docx`.

**Done** (branch `verify-work` cả 2 repo):

| # | Gap | Commit | Note |
|---|---|---|---|
| 1 | Polling 60s → 15s (ch.4.5) | chat-system:e460ece | `POLL_INTERVAL_MS` single source |
| 2 | ChatOps 6/10 → 10/10 (ch.4.3) | chat-system:8b50dcc | /status /results /help /feedback + 8 test mới |
| 3 | Guardrail 2-layer → 4-layer docs (ch.4.4.2) | chat-system:1e3cd22 | docs rewrite, code đã có sẵn auth+schema |
| 4 | Security Gate stage 7 (ch.4.2) | sast-action:0577b81 | Composite + workflow job, block PR nếu critical |
| 5 | CodeQL chưa wire (ch.4.2) | sast-action:a1a2328 | Add CodeQL cho java/python/node/go |
| 6 | MCP misnomer → MCP thật (ch.3.2) | chat-system:ed175ec | `fastmcp` 8 tool, 13 test pass |
| 7 | Docs/spec alignment | đang làm | 02/08/09 update, REQUIREMENTS đồng bộ |

**Live verify pending**:
- Step 4 + 5 chạy thật trên CI khi `sast-action verify-work` merge về `master` (sample-python sẽ tự pick up).
- Step 6 chạy thật khi cấu hình Claude Desktop với config trong `docs/mcp-server.md`.

## Tag v0.2.0

Điều kiện tag:
- [ ] V2.5 verify end-to-end
- [ ] Update CHANGELOG.md v0.2.0 section
- [ ] Tag sast-action `v0.2.0` (push trigger `release.yml` build Docker image)
- [ ] Inheritor sample-python switch ref `@master` → `@v0.2.0`
- [ ] Defense slide đã update

---

## v0.3 vision (post-defense, ~1 tháng sau)

### Multi-tenant runtime
- Wire `Project.github_token`, `gemini_api_key` per-project
- Fernet encryption at-rest cho credentials
- Update poller + processor đọc từ Project thay env

### MCP server thật
- Implement MCP protocol wrapper qua `fastmcp` SDK
- Expose tool: `list_findings`, `get_finding_detail`, `analyze_with_ai`, `mark_resolved`, `trigger_rescan`
- Claude Desktop / Cursor có thể plug in → dev hỏi natural language

### Polish
- Lazy-load Chat tab + Reports tab → giảm bundle
- Rename `mcp/` → `gateway/` để khỏi misleading
- Add actionlint CI cho sast-action repo
- Migrate Safety syntax sang 3.x

### Optional features
- Slack/Discord webhook destination (alternative cho email)
- PR comment với top 5 finding (qua GitHub API)
- VS Code extension hiển thị finding inline
- Multi-org support (cochecheee + other GitHub orgs)

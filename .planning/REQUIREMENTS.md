# System Requirements: Security-Integrated CI/CD System

> Status: **V2.7 alignment** (2026-05-15). Bản này khớp implementation hiện tại.
> Diff với bản gốc (master `914d2d9`) ghi chú trong "Decision log" cuối file.

## Functional Requirements

### 1. CI/CD Pipeline & SAST Integration
- [x] Trigger pipeline từ GitHub Events (Push, Pull Request, workflow_dispatch).
- [x] Tích hợp 5 SAST/SCA tool xuyên ngôn ngữ:
      `Semgrep` (universal), `CodeQL` (java/python/node/go, V2.7),
      `SpotBugs` (java), `ESLint-security` (node), `OWASP Dep-Check` (java).
      Plus `Trivy` (FS + image, all), `Bandit` (python), `Safety` (python),
      `gosec` (go), `npm-audit` (node) làm SCA bổ sung.
- [x] Upload kết quả SARIF / XML / JSON lên GitHub Artifacts với prefix
      `sast-reports-<run_number>`.
- [x] **Security Gate** (V2.7) block PR khi `count(critical) ≥ 1` hoặc
      `count(high) ≥ 5`. Threshold configurable. Implementation:
      `sast-action/actions/security-gate/`.

### 2. MCP Gateway + MCP Server (V2.7 dual-protocol)

**REST Gateway** (`mcp/src/main.py` FastAPI):
- [x] Tự động fetch artifacts từ GitHub Actions sau khi pipeline complete
      (webhook `/webhook/pipeline-complete` + fallback poller 300s).
- [x] Normalize SARIF / XML / JSON về unified schema `Finding` (entities.py).
      Hỗ trợ Semgrep, CodeQL, SpotBugs, ESLint, Trivy, Bandit, Safety,
      OWASP Dep-Check, OWASP ZAP normalizers.
- [x] **Sanitization (Layer 3)**: `detect-secrets` + email + IPv4 regex
      scrub trước khi store + trước khi gửi LLM.
- [x] **Prompt Injection Guardrails (Layer 4)**: 9 pattern reject +
      truncate 2000 chars + strip control chars.
- [x] Enrichment: CWE id (từ SARIF rule properties), CVSS score
      (DepCheck cvssv3/v2, Trivy NVD V3Score), OWASP mapping (raw_data).

**Anthropic MCP Server** (`mcp/src/mcp_server.py`, V2.7):
- [x] Implement Model Context Protocol qua `fastmcp` SDK.
- [x] Expose 8 tool: `list_findings`, `get_finding`, `explain_finding`,
      `approve_finding`, `revoke_finding`, `list_pipelines`,
      `get_stats_overview`, `trigger_scan`.
- [x] Hỗ trợ 2 transport: stdio (Claude Desktop) + HTTP+SSE (MCP Inspector).

### 3. AI Analysis & Remediation (LLM Orchestrator)
- [x] Gemini `gemini-2.5-flash` (configurable qua `GEMINI_MODEL` env).
- [x] Vulnerability explanation tiếng Việt (`SYSTEM_INSTRUCTION` bắt buộc VI).
- [x] Remediation diff (Unified Diff) dựa trên 15 dòng context từ
      `GitHubClient.fetch_file_content`.
- [x] Output validation qua Pydantic `AnalysisOutput` schema
      (severity enum, confidence enum).

### 4. Web Dashboard (ChatOps integrated)
- [x] Polling **15 giây** (V2.7 — `POLL_INTERVAL_MS = 15_000`).
- [x] Severity chart (donut + heatmap + sparkline) trên Overview page.
- [x] ChatOps 10 lệnh (V2.7 +4 lệnh):
      `/status`, `/scan`, `/results`, `/explain`, `/fix`, `/rerun`,
      `/approve`, `/revoke`, `/report`, `/help`, `/feedback`.
- [x] Phân quyền: **JWT demo login với role developer/security_lead/admin**.
      Mapping `COMMAND_ROLES` trong `api/chat.py`.
      **Deviation từ spec gốc**: spec yêu cầu "GitHub team membership"
      — đã defer roadmap v0.3 (OAuth + team API), demo dùng JWT để
      defense panel test được role flow mà không cần GitHub setup.

### 5. Storage Layer
- [x] SQLite (dev, `mcp.db`) + Postgres (production Render free,
      V2.6 — `databases: mcp-db` trong render.yaml).
- [x] DATABASE_URL validator rewrite `postgres://` → `postgresql+asyncpg://`.
- [x] Schema migration auto trong `core/db.init_db` — detect naive
      TIMESTAMP / INT4 cũ → drop+recreate (Postgres only, SQLite ignore).

## Non-Functional Requirements
- **Security**: 4-layer guardrail (Auth JWT + Schema Pydantic + Content
  scrub + Prompt injection). Production fail-fast khi `SECRET_KEY` /
  `CI_WEBHOOK_TOKEN` / `CORS_ORIGINS` default hoặc empty.
- **Reliability**: GitHub poller fallback 5 phút nếu webhook fail.
  Gemini retry 3 lần exponential backoff 429/503.
- **Scalability**: Composite GitHub Actions tách per-language step;
  thêm ngôn ngữ mới = add 1 `if: inputs.language == 'X'` block.
  MCP server tool surface mở rộng = add `@mcp.tool` decorator.
- **Performance**: AI fix lazy (cache `finding.ai_analysis`). Polling
  15s frontend; backend GitHub poller 300s để không hit rate limit.

## Extension features (ngoài scope báo cáo tiến độ 1)

V2.2/V2.3/V2.4 thêm để hệ thống thực sự DevSecOps complete:

- **V2.2 CD**: composite `build-image` (docker build + Trivy scan + push
  Hub) + `deploy-staging` (POST Render Deploy Hook). `cd:` job sau gate
  pass mới chạy.
- **V2.3 DAST**: composite `run-dast` chạy OWASP ZAP baseline 5 phút
  qua staging URL post-deploy. `ZapJsonNormalizer` ingest → Runtime tab.
- **V2.4 Monitor**: uptime check 5 phút interval ping staging, alert
  email khi down ≥ threshold; recovered alert khi back up.
  Sentry hook optional. Prune UptimeCheck > 7 ngày để giữ Postgres
  free 256MB.

## Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-04-?? | "MCP Gateway" naming kept | Master Control Plane legacy; pivot Anthropic MCP defer |
| 2026-05-?? | Repo split 1→3 (chat-system + sast-action + sample-python) | Template pattern: 1 mcp instance serve N inheritor |
| 2026-05-08 | v0.1.0 defense-ready với 6 page + 200 pytest | Original 1-week deadline |
| 2026-05-13 | V2.2 CD shipped end-to-end (184 finding ingested) | Prove inheritor flow |
| 2026-05-14 | V2.3 DAST + V2.4 Monitor + V2.6 Postgres | DevSecOps complete |
| 2026-05-15 | **V2.7 docx alignment** | Audit gap report ch.3.2 + 4 vs code. 5 wire + 2 doc commit. MCP server thật bằng `fastmcp`. |

## Deviation từ spec gốc (master `914d2d9`)

| Spec gốc | Hiện trạng | Lý do |
|---|---|---|
| "GitHub team membership" cho RBAC | JWT demo role | OAuth flow + team API ~2 ngày, defer v0.3. JWT cho phép demo flow đầy đủ mà không cần GitHub setup |
| "SQLite database" duy nhất | SQLite dev + Postgres prod (V2.6) | Render free SQLite reset mỗi redeploy. Postgres free 256MB persist 90 ngày |
| Single repo monolithic | 3 repo (chat-system + sast-action + sample-python) | Template pattern hỗ trợ multi-inheritor. Tách `sast-action` thành reusable library |
| "MCP (Model Context Protocol)" | V2.7 implement thật + giữ REST gateway role | Dual-protocol: REST cho dashboard, MCP cho AI client |

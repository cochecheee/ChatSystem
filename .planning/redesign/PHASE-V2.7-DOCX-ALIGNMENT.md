# Phase V2.7 — Báo cáo tiến độ docx alignment

**Branch**: `verify-work` (từ `ft/imp-fe`)
**Mục tiêu**: Đóng gap giữa code hiện tại và `Nhom04_BaoCaoTienDo1_fixed_1.docx`
**Driver**: Defense panel sẽ đọc docx → mọi mismatch giữa spec docx và demo code sẽ bị hỏi
**Ngày bắt đầu**: 2026-05-15

## Gap chính (từ analysis docx ch.3-4)

| # | Spec docx | Hiện trạng | Gap |
|---|---|---|---|
| G1 | Ch.4.5 polling real-time 15s | backend 300s, frontend 30-60s | Đổi env + frontend interval |
| G2 | Ch.4.3 ChatOps 10 lệnh: /status /scan /results /explain /fix /rerun /approve /report /help /feedback | Có 6/10, thiếu 4 | Thêm /status /results /help /feedback handlers |
| G3 | Ch.4.2 Stage 7 Security Gate (block PR nếu CRITICAL) | Không có | Thêm job vào `sast-action/.github/workflows/sast-ci.yml` |
| G4 | Ch.4.2 5 SAST tool: Semgrep + CodeQL + ESLint + SpotBugs + OWASP Dep-Check | Đang chạy Semgrep + Trivy + Bandit + Safety | Wire CodeQL + ESLint + OWASP Dep-Check vào `sast-suite/action.yml` |
| G5 | Ch.3.2 + 4.1 MCP = Anthropic Model Context Protocol thật | REST gateway thuần | Thêm `mcp/src/mcp_server.py` dùng `fastmcp` SDK |
| G6 | Ch.4 architecture 1-repo monolithic | 3-repo split (chat-system + sast-action + sample-python) | Document pivot ở docx |
| G7 | Ch.4 + Ch.2.1.3 scope SAST only | Code có V2.2 CD + V2.3 DAST + V2.4 Monitor | Document "mở rộng vượt scope" ở docx |
| G8 | Ch.4.4 4-layer guardrail (auth, schema, content, prompt) | 2 layer rõ (Scrubbing + InjectionGuardrail) | Document 4-layer mapping rõ ràng (không cần thêm code) |

## Thứ tự execute (cheap → expensive)

### Step 1 — G1: Polling 15s
- **Files**: `render.yaml` (POLLING_INTERVAL_SECONDS=15), `dashboard/src/pages/*.tsx` (setInterval 15000), `dashboard/src/App.tsx`
- **Verify**: grep `setInterval.*15` trong dashboard; `render.yaml` có `value: "15"`
- **Risk**: tăng tải GitHub API → check rate-limit budget
- **Effort**: 15'
- **Commit**: `chore(spec): align polling to 15s per docx ch.4.5`

### Step 2 — G2: 4 commands còn thiếu
- **Files**: `mcp/src/services/command_service.py` (thêm `_handle_status, _handle_results, _handle_help, _handle_feedback`), `mcp/src/api/chat.py` (COMMAND_ROLES map), tests
- **Behavior**:
  - `/status [repo]` → trả về workflow run đang chạy hoặc latest run status (GitHub API)
  - `/results [repo] [run_id]` → summary findings của run gần nhất (severity counts + top 5)
  - `/help` → liệt kê 10 lệnh + roles
  - `/feedback [finding_id] [text]` → ghi vào table `command_feedback` mới hoặc log
- **Verify**: pytest `tests/test_chat_api.py`; manual curl `/api/chat/command`
- **Effort**: 2-3h
- **Commit**: `feat(chat): add /status /results /help /feedback per docx ch.4.3`

### Step 3 — G8: Document 4-layer guardrail
- **Files**: `docs/guardrails.md` cập nhật mapping 4-layer; `mcp/src/core/guardrails.py` thêm comment chú thích layer
- **Verify**: docs có 4 section rõ ràng (auth/schema/content/prompt)
- **Effort**: 30'
- **Commit**: `docs(guardrails): explicit 4-layer mapping per docx ch.4.4`

### Step 4 — G3 (cross-repo `sast-action`): Security Gate
- **Branch khác repo**: tạo `verify-work` branch trong `D:\School\DoAnTotNghiep\sast-action`
- **Files**: `sast-action/.github/workflows/sast-ci.yml` (thêm job `security-gate` sau `sast`, parse SARIF với jq, fail nếu CRITICAL > 0)
- **Threshold config**: input `gate_fail_on=critical` default, allow override
- **Verify**: push test commit vào sample-python với 1 critical → CI fail; remove critical → CI pass
- **Effort**: 4-6h (gồm 1-2 lần verify qua CI)
- **Commit ở sast-action**: `feat(gate): block PR if SARIF contains critical findings per docx ch.4.2 stage 7`

### Step 5 — G4 (cross-repo `sast-action`): Wire 3 tool còn thiếu
- **Files**: `sast-action/actions/sast-suite/action.yml`
  - Add CodeQL: `github/codeql-action/init` + `analyze` (Python first, Java/JS fallback)
  - Add ESLint security plugin (when `language=node`)
  - Add OWASP Dep-Check (already in tree cho Java) — verify chạy được Python qua `--enableExperimental`
- **Output**: thêm artifacts `codeql.sarif`, `eslint-security.sarif`, `depcheck.json` vào `sast-reports-`
- **Update profile**: `mcp/config/profiles/github-actions-default.yml` đã prefix-match, không cần đổi
- **Verify**: trigger CI sample-python → check artifact zip có 4 SARIF + dep-check.json; mcp dashboard hiển thị tool name `codeql/eslint/dependency-check`
- **Effort**: 4-6h
- **Commit ở sast-action**: `feat(sast): wire CodeQL + ESLint + OWASP Dep-Check per docx ch.4.2`

### Step 6 — G5: MCP server thật bằng fastmcp
- **Files**:
  - `mcp/requirements.txt` add `fastmcp`
  - `mcp/src/mcp_server.py` — entry point `FastMCP("sast-mcp")` với tools wrap DB qua repositories
  - Tools tối thiểu (8):
    - `list_findings(severity?, category?, status?, limit=50)`
    - `get_finding(id)`
    - `explain_finding(id)` — invoke LLMAnalysisService
    - `approve_finding(id, justification)`
    - `revoke_finding(id, justification)`
    - `list_pipelines(limit=20)`
    - `get_stats_overview()`
    - `trigger_scan()` — dispatch workflow
  - `mcp/Dockerfile` add optional MCP CMD
  - Run mode: stdio (cho Claude Desktop) + HTTP+SSE (cho demo)
- **Verify**:
  - MCP Inspector connect stdio → list_tools trả 8 tools
  - Claude Desktop config `claude_desktop_config.json` → ask "show critical findings" → tool call thành công
  - Existing FastAPI + dashboard vẫn chạy bình thường (dual-protocol)
- **Risk**: dual-event-loop async — chạy 2 process safer than threading
- **Effort**: 2-3 ngày (gồm Inspector + Claude Desktop verify)
- **Commit**: `feat(mcp): implement Anthropic MCP server with 8 tools per docx ch.3.2`

### Step 7 — B1-B4: Document pivot trong docx
- Cập nhật docx (manual edit Word) hoặc viết delta vào `docs/project/`:
  - **B1**: Thêm section "4.6 Mở rộng vượt scope ban đầu" — V2.2 CD, V2.3 DAST/ZAP, V2.4 Monitor
  - **B2**: Thêm section "4.7 Quyết định tách 3 repo" — template pattern justification
  - **B3**: Update `.planning/REQUIREMENTS.md` để khớp thực tế + log changes
  - **B4**: Document GitHub-team RBAC là roadmap v0.3, JWT demo là current
- **Effort**: 4-6h docx editing
- **Commit**: `docs: align REQUIREMENTS + docs/project with implemented architecture`

## Acceptance criteria (Phase V2.7 done)

- [ ] Demo path: developer push code → CI chạy 5 SAST tool (CodeQL+ESLint+SpotBugs+Semgrep+DepCheck) → Security Gate block nếu critical → MCP server expose qua Claude Desktop hỏi natural language → dashboard polling 15s update real-time → 10 ChatOps lệnh đầy đủ
- [ ] Báo cáo tiến độ 2 (docx): kiến trúc match implementation, có section giải thích mọi pivot
- [ ] All existing pytest pass (200+)
- [ ] No regression V2.1-V2.6: webhook ingest, AI fix VI, Monitor uptime, Postgres persist

## Out-of-scope (defer v0.3)

- Multi-tenant runtime (per-project credentials)
- Fernet encryption at-rest
- GitHub OAuth + team membership lookup (giữ JWT demo)
- VS Code extension / PR comment integration
- Rename `mcp/` → `gateway/` (giữ nguyên vì đã match docx "MCP")

## Tracking

| Step | Status | Commit SHA | Verified |
|---|---|---|---|
| 1 G1 polling 15s | DONE | e460ece | TS check pass, grep all polls = POLL_INTERVAL_MS |
| 2 G2 4 commands | DONE | 8b50dcc | 208/208 pytest pass (incl 8 new) |
| 3 G8 guardrail docs | DONE | — | guardrails.md rewrite 4-layer + 24/24 tests pass |
| 4 G3 Security Gate (sast-action) | DONE | sast-action:0577b81 | YAML lint pass + Python jq-equiv smoke (1 crit→fail, clean→pass). Live CI verify deferred to merge time. |
| 5 G4 CodeQL wire (sast-action) | DONE | sast-action:a1a2328 | YAML valid, 5 CodeQL steps added; ESLint+SpotBugs+DepCheck đã có từ V2.1. Live CI verify deferred. |
| 6 G5 MCP server thật | TODO | — | — |
| 7 B1-B4 docx alignment | TODO | — | — |

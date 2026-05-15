# 08 — Limitations & Known Issues

Honest assessment — không phải marketing.

## Infra

### ~~SQLite ephemeral trên Render free tier~~ → V2.6 đã fix
- **Trước**: `/tmp/mcp.db` reset mỗi redeploy → mất Project + Finding + UptimeCheck
- **Fix** (V2.6, chờ Sync): switch sang Render free Postgres 256MB qua `databases: mcp-db` ở render.yaml. config.py rewrite `postgres://` → `postgresql+asyncpg://`. Data persist qua redeploy.
- **Limit còn lại**: Postgres free hết hạn 90 ngày → cần upgrade $7/mo paid hoặc migrate Supabase free vĩnh viễn.

### Cold start ~30s
- **Impact**: Request đầu sau 15 phút idle bị timeout nếu client `--max-time` < 60s
- **Mitigation**: External cron ping `/health` mỗi 10 phút
- **Acceptable cost**: $0/mo

### Single region (Singapore)
- **Impact**: Latency VN ~50ms, US ~200ms. Đổi region cần delete + recreate service
- **Acceptable**: Mục tiêu chính VN

## Backend logic

### Multi-tenant scaffolding nhưng runtime single-tenant
- **State**: `Project` entity có 9 column credentials nhưng runtime đọc `GITHUB_TOKEN`/`OWNER`/`REPO` từ env
- **POST /projects** chỉ persist `name + github_url`, các field khác bị drop silently
- **Resolve v0.3**: Wire per-project credentials + Fernet encryption ở rest

### Plain-text credentials
- **State**: Nếu future multi-tenant wire on → `Project.github_token`, `gemini_api_key` lưu plaintext
- **Resolve v0.3**: Fernet encrypt at-rest, decrypt khi load vào memory

### Dep-Check Java path requires gradlew + plugin
- **State**: `actions/sast-suite` Java step gọi `./gradlew compileJava spotbugsMain` + `dependencyCheckAnalyze`
- **Limitation**: Inheritor Java repo phải có gradlew + plugin config. Maven không support.
- **Resolve**: Add Maven plugin path detection ở composite, hoặc separate `sast-suite-maven` composite

### Safety pinned `<3`
- **Reason**: Safety 3.x đổi CLI `check` → `scan`, flag khác
- **Cost**: Không dùng được tính năng mới của Safety 3 (auto-fix, policy file YAML)
- **Resolve**: Migrate sang `safety scan` syntax khi có thời gian

## Frontend

### Dashboard chưa deploy
- **State**: Phải `npm run dev` local mới thấy data
- **Resolve V2.5**: Deploy Static Site lên Render (build artifact `dist/` + serve)

### Pipelines tab trùng GitHub Actions UI
- **State**: Tab "Pipelines" hiện list workflow run — y hệt UI native GitHub Actions
- **Value marginal**: User có thể vào trực tiếp `/actions` tab của GitHub
- **Acceptable**: Giữ làm proof-of-concept polling, có thể remove sau

### 305KB JS bundle
- **State**: Vite build chunk ~305KB gzipped first-load
- **Impact**: First paint chậm trên 3G
- **Resolve deferred**: Lazy-load Chat tab + Reports tab → giảm ~150KB initial

## Naming / Architecture

### ~~"MCP" misnomer~~ → V2.7 fixed
- **Trước V2.7**: Tên folder `mcp/` + "MCP Gateway" docs gây hiểu nhầm với Anthropic Model Context Protocol mà code chỉ có REST.
- **V2.7 (2026-05-15)**: Implement MCP server thật bằng `fastmcp` SDK. `mcp/src/mcp_server.py` expose 8 tool (list_findings, get_finding, explain_finding, approve/revoke, list_pipelines, stats, trigger_scan). Dual-protocol: FastAPI cho dashboard + MCP cho Claude Desktop / Cursor.
- **Remaining work**: Implement **resources** + **prompts** dimension của MCP (hiện chỉ có **tools**). Roadmap v0.3.
- Xem [`docs/mcp-server.md`](../mcp-server.md).

## Security

### CI webhook auth tùy chọn
- **State**: Nếu `CI_WEBHOOK_TOKEN` rỗng ở server → auth disabled, ai cũng POST được
- **Production setting**: Phải set token random 32+ chars
- **Risk**: Tự inject finding giả nếu attacker biết URL

### Gemini API key không rate-limited server-side
- **State**: User unauth có thể call `/findings/{id}/analyze` → tốn quota Gemini
- **Resolve**: JWT auth required cho analyze endpoint (đã có decorator nhưng có thể bypass route?)
- **Verify**: Test 401 khi không có Bearer token

### CORS wildcard ở development
- **State**: `APP_ENV=development` → `allow_origins=["*"]`
- **Acceptable**: Local dev only. Render set `APP_ENV=production` → `CORS_ORIGINS` explicit

## Documentation

### Memory in `.planning/` chỉ phục vụ session
- **State**: `.planning/redesign/*.md` là snapshot per session
- **Not authoritative**: Project docs chính thức ở `docs/project/`
- **Update sync**: Khi commit feature lớn, update `07-history.md` + `09-roadmap.md`

### Inheritor guide chưa cover Java Maven
- **State**: `docs/inheritor-guide.md` mặc định Gradle
- **Resolve**: Add Maven section khi có request

## DAST chưa wire
- **V2.3 sẽ làm**: OWASP ZAP baseline scan
- **Tab Runtime hiện trống** ở dashboard

## sast-action không có CI riêng
- **State**: Đổi `actions/sast-suite/action.yml` không có lint guard
- **Risk**: Push broken action → tất cả inheritor break đồng thời
- **Resolve**: Add `actionlint` workflow ở `cochecheee/sast-action` repo

## Defense risk

| Risk | Probability | Mitigation |
|---|---|---|
| Panel hỏi "MCP là gì?" | High | Có disclaimer sẵn ở slide. Nói rõ pivot |
| Demo cold start fail | Medium | Pre-warm trước demo. Có fallback local |
| Internet GitHub API rate-limit | Low | PAT scope đúng, có cache local |
| Gemini API quota | Low | Free tier 60 req/min đủ cho demo |

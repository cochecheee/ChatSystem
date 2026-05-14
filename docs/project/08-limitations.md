# 08 — Limitations & Known Issues

Honest assessment — không phải marketing.

## Infra

### SQLite ephemeral trên Render free tier
- **Impact**: Mỗi redeploy + container restart → mất hết Project, Pipeline, Finding, AI cache
- **Mitigation**: Webhook auto re-ingest sau CI lần tiếp theo (~5 phút)
- **Resolve**: Upgrade Render Postgres free 90 ngày (`postgresql+asyncpg://`) hoặc Starter plan + persistent disk

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

### "MCP" misnomer
- **Issue**: Tên folder `mcp/` + "MCP Gateway" trong docs gây hiểu nhầm
- **Reality**: Đây là REST API gateway, KHÔNG phải Model Context Protocol server của Anthropic
- **Resolve options**:
  - A. Rename `mcp/` → `gateway/` / `backend/` (~30 phút refactor)
  - B. Implement MCP thật (2-3 ngày, biến thành AI-native tool — recommend cho thesis)
  - C. Add disclaimer ở README + slide
- **Decision**: Defer post-defense, document clearly ở [02-architecture.md](02-architecture.md)

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

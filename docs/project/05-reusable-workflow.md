# 05 — Reusable Workflow Contract

## Inheritor onboarding

Bất kỳ project Java/Python/Node/Go nào muốn có SAST pipeline → thêm 1 file 10 dòng:

```yaml
# .github/workflows/security.yml
name: Security
on:
  push:
    branches: [main, develop]
  pull_request:
  workflow_dispatch:

# Caller PHẢI explicitly grant permissions reusable workflow request
permissions:
  contents: read
  security-events: write
  actions: read

jobs:
  security:
    uses: cochecheee/sast-action/.github/workflows/sast-ci.yml@master
    with:
      language: python   # java | python | node | go
      pipeline_status: passed
    secrets:
      dashboard_url:   ${{ secrets.MCP_GATEWAY_URL }}
      dashboard_token: ${{ secrets.MCP_WEBHOOK_TOKEN }}
```

Set 2 secret ở Settings → Actions → Secrets → done.

## Contract

### Inputs (passed via `with:`)

| Input | Type | Required | Default | Mô tả |
|---|---|---|---|---|
| `language` | string | ✅ | — | `java` \| `python` \| `node` \| `go` |
| `semgrep_config` | string | ❌ | `auto` | Semgrep ruleset (p/owasp-top-ten, ...) |
| `pipeline_status` | string | ❌ | `passed` | Override status gửi dashboard |
| `deploy` | bool | ❌ | `false` | **V2.2** — bật CD: build image + push Hub + redeploy Render |
| `image_repo` | string | ❌ if deploy=false | `''` | **V2.2** — Docker Hub repo (`cochecheee/<repo>`) |
| `dockerfile` | string | ❌ | `Dockerfile` | **V2.2** — Path Dockerfile relative đến `build_context` |
| `build_context` | string | ❌ | `.` | **V2.2** — Docker build context |

### Secrets (passed via `secrets:`)

| Secret | Required | Mô tả |
|---|---|---|
| `dashboard_url` | ❌ | MCP gateway URL. Trống → skip notify với warning. |
| `dashboard_token` | ❌ | Bearer token. Match `CI_WEBHOOK_TOKEN` ở mcp. |
| `nvd_api_key` | ❌ | Chỉ Java Dep-Check. Tăng tốc download NVD database. |
| `docker_username` | ❌ if deploy=false | **V2.2** — Docker Hub username |
| `docker_password` | ❌ if deploy=false | **V2.2** — Docker Hub access token (NOT password) |
| `render_deploy_hook` | ❌ | **V2.2** — Render Deploy Hook URL (Settings → Deploy Hook) |

**Vì sao `dashboard_url` là secret chứ không phải input?** GitHub cấm `${{ secrets.* }}` trong block `with:` của reusable workflow caller. Phải đi qua `secrets:` block. Reusable workflow declare nó như secret rồi bind vào job env để dùng.

## Tools per language (verified)

| Lang | Universal | Specific |
|---|---|---|
| `java` | Semgrep + Trivy-FS | SpotBugs + OWASP Dep-Check |
| `python` | Semgrep + Trivy-FS | Bandit + Safety (`<3`) |
| `node` | Semgrep + Trivy-FS | ESLint-security + npm-audit |
| `go` | Semgrep + Trivy-FS | gosec |

Mở `actions/sast-suite/action.yml` để xem từng step. Tool nào skip dựa trên `if: ${{ inputs.language == 'X' }}`.

## Artifact output

Sau khi suite chạy xong, upload 1 artifact:

```
Name:  sast-reports-<run_number>
Files: semgrep.sarif
       trivy-fs.sarif
       bandit.sarif        (Python)
       safety.json         (Python)
       spotbugs.sarif      (Java)
       depcheck.json       (Java)
       eslint.sarif        (Node)
       npm-audit.json      (Node)
       gosec.sarif         (Go)
```

**Profile match**: mcp `config/profiles/github-actions-default.yml` đã có prefix `sast-reports-` để pickup artifact này. Nếu mày tự đổi tên artifact ở action → phải update profile tương ứng.

## V2.2 — Bật CD (deploy Render staging)

Sample-python production-style workflow:

```yaml
jobs:
  security:
    uses: cochecheee/sast-action/.github/workflows/sast-ci.yml@master
    with:
      language: python
      deploy: true
      image_repo: cochecheee/sample-python
      dockerfile: Dockerfile
      build_context: .
    secrets:
      dashboard_url:      ${{ secrets.MCP_GATEWAY_URL }}
      dashboard_token:    ${{ secrets.MCP_WEBHOOK_TOKEN }}
      docker_username:    ${{ secrets.DOCKER_USERNAME }}
      docker_password:    ${{ secrets.DOCKER_PASSWORD }}
      render_deploy_hook: ${{ secrets.RENDER_DEPLOY_HOOK }}
```

Pipeline mới có 2 job:

```
sast: ─── chạy SAST tools, notify dashboard (cũ)
   │
   ▼ needs: sast
cd:  ─── build image + Trivy image scan + push Docker Hub + POST Render hook
```

Setup 1 lần (xem [04-deploy.md](04-deploy.md#staging-service-cho-inheritor) cho chi tiết):

1. **Docker Hub Access Token**: hub.docker.com → Account Settings → Security → New Access Token
2. **Render staging service**: New + → Web Service → "Deploy existing image" → `docker.io/cochecheee/sample-python:latest`
3. **Deploy Hook URL**: Render service → Settings → Deploy Hook → copy URL
4. **Add 3 GitHub secret** vào inheritor repo:
   - `DOCKER_USERNAME` = `cochecheee`
   - `DOCKER_PASSWORD` = Hub Access Token
   - `RENDER_DEPLOY_HOOK` = Render Deploy Hook URL

Sau đó: push commit inheritor → ~5 phút sau app live tại `https://sample-python-XXX.onrender.com`.

## Composite actions độc lập

Inheritor có thể `uses:` riêng từng composite nếu muốn custom pipeline:

### A. Chỉ notify (V0.1 legacy)
```yaml
- uses: cochecheee/sast-action@master   # root action.yml
  with:
    dashboard-url:   ${{ secrets.MCP_GATEWAY_URL }}
    dashboard-token: ${{ secrets.MCP_WEBHOOK_TOKEN }}
    pipeline-status: passed
```

### B. Chỉ chạy SAST suite (không notify)
```yaml
- uses: cochecheee/sast-action/actions/sast-suite@master
  with:
    language: python
- uses: actions/upload-artifact@v4
  with:
    name: my-sast-reports
    path: reports/
```

### C. Gom SARIF + POST trực tiếp (bypass GitHub artifact)
```yaml
- uses: cochecheee/sast-action/actions/sast-suite@master
  with:
    language: python
    upload-individual-artifacts: 'false'
- uses: cochecheee/sast-action/actions/aggregate-sarif@master
  with:
    reports-dir: reports
    dashboard-url:    ${{ secrets.MCP_GATEWAY_URL }}
    dashboard-api-key: ${{ secrets.CI_API_KEY }}
    project-id: 1
```

### D. Chỉ build + push image (skip SAST + deploy)
```yaml
- uses: cochecheee/sast-action/actions/build-image@master
  with:
    image_repo: cochecheee/sample-python
    docker_username: ${{ secrets.DOCKER_USERNAME }}
    docker_password: ${{ secrets.DOCKER_PASSWORD }}
```

### E. Chỉ trigger Render redeploy
```yaml
- uses: cochecheee/sast-action/actions/deploy-staging@master
  with:
    render_deploy_hook: ${{ secrets.RENDER_DEPLOY_HOOK }}
    service_name: sample-python
```

## Versioning

| Tag/Ref | Status | Cách dùng |
|---|---|---|
| `@master` | Active dev | Cho inheritor đang theo dõi changes |
| `@v0.2.0` | Pending | Tag chính thức sau khi V2.5 verify |
| `@v0.1.0` | Legacy | Single-action notify-only (root `action.yml`) |

Inheritor production nên pin tag cụ thể (`@v0.2.0`) để không bị break khi sast-action update.

## Common pitfall

### 1. `Invalid workflow file: Unrecognized named-value: 'secrets'`

Caller dùng `secrets.X` trong `with:` block:

```yaml
# ❌ WRONG
jobs:
  security:
    uses: cochecheee/sast-action/.github/workflows/sast-ci.yml@master
    with:
      dashboard_url: ${{ secrets.MCP_GATEWAY_URL }}   # cấm
```

Fix: di chuyển sang `secrets:`:

```yaml
# ✅ CORRECT
    secrets:
      dashboard_url: ${{ secrets.MCP_GATEWAY_URL }}
```

### 2. `Error calling workflow ... requesting 'actions: read, security-events: write'`

Caller không grant permissions. Add ở workflow level:

```yaml
permissions:
  contents: read
  security-events: write
  actions: read
```

### 3. `Disallowed CORS origin`

Dashboard call mcp từ origin không có trong `CORS_ORIGINS` env. Add origin vào Render env var, redeploy.

### 4. 0 findings sau khi CI pass

Artifact name không match profile. Check:
- mcp logs: artifact bị skip với "name not in profile"
- mcp/config/profiles/github-actions-default.yml: prefix `sast-reports-` có không
- sast-suite output artifact name: `sast-reports-<run_number>`

### 5. Cold start timeout

Request đầu sau idle mất 30-60s. Client phải set `--max-time 60` trở lên, hoặc retry.

## Mở rộng — thêm ngôn ngữ mới

Thêm `csharp`, `ruby`, `rust`... = thêm 1 block `if: inputs.language == 'X'` ở `actions/sast-suite/action.yml`:

```yaml
- name: Brakeman (Ruby)
  if: ${{ inputs.language == 'ruby' }}
  shell: bash
  run: |
    gem install brakeman
    brakeman -o reports/brakeman.json --no-progress || true
```

Không cần đụng reusable workflow hay inheritor.

## Mở rộng — thêm step CD/DAST/Monitor (V2.2+)

Sẽ thêm composite mới:
- `actions/build-image/` — build container + Trivy scan (V2.2)
- `actions/deploy-staging/` — push to Render API (V2.2)
- `actions/run-dast/` — OWASP ZAP baseline (V2.3)
- `actions/notify-monitor/` — Sentry + email alert (V2.4)

Reusable workflow `sast-ci.yml` sẽ chain các composite này tùy theo input flags.

# Inheritor Guide — Plug your repo into chat-system in 5 minutes

> Mục tiêu: project bất kỳ (Java/Python/Node/Go) chỉ cần 1 file workflow ngắn để có toàn bộ SAST scan + push findings về dashboard.

---

## Prerequisites

- chat-system instance đã chạy ở 1 URL public (Render free tier theo `docs/cd-setup.md`).
- Bạn đã set 2 GitHub Secrets ở repo của bạn:
  - `MCP_GATEWAY_URL` — base URL của chat-system, ví dụ `https://chat-mcp.onrender.com`
  - `MCP_WEBHOOK_TOKEN` — match với `CI_WEBHOOK_TOKEN` trong chat-system `.env`
- (Java only) `NVD_API_KEY` cho OWASP Dependency-Check, đăng ký free tại https://nvd.nist.gov/developers/request-an-api-key

---

## Quickstart

Tạo file `.github/workflows/security.yml`:

```yaml
name: Security
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  security:
    uses: cochecheee/sast-action/.github/workflows/sast-ci.yml@v0.2.0
    with:
      language: python    # java | python | node | go
      dashboard_url: ${{ secrets.MCP_GATEWAY_URL }}
    secrets:
      dashboard_token: ${{ secrets.MCP_WEBHOOK_TOKEN }}
      nvd_api_key:     ${{ secrets.NVD_API_KEY }}     # Java only
```

Đó là toàn bộ. Push code → CI chạy SAST → findings vào dashboard.

---

## Tools per language

| Language | Tools |
|---|---|
| `java`   | Semgrep, Trivy FS, SpotBugs, OWASP Dep-Check |
| `python` | Semgrep, Trivy FS, Bandit, Safety |
| `node`   | Semgrep, Trivy FS, ESLint security plugin, npm audit |
| `go`     | Semgrep, Trivy FS, gosec |

Tất cả output SARIF (Semgrep, Trivy, SpotBugs, ESLint, gosec, Bandit) hoặc JSON (Dep-Check, Safety, npm-audit). Lenient SARIF parser của chat-system chấp nhận mọi biến thể.

---

## Override / extend

### Custom Semgrep ruleset

```yaml
with:
  language: python
  semgrep_config: 'p/owasp-top-ten'   # default: 'auto'
```

Hoặc full registry: `r/python.flask` , file local `.semgrep.yml`, ...

### Force pipeline status

Mặc định status="passed" nếu workflow xanh. Override:

```yaml
with:
  pipeline_status: 'gate_failed'
```

### Tự dùng composite action (không qua reusable workflow)

```yaml
jobs:
  custom:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: cochecheee/sast-action/actions/sast-suite@v0.2.0
        with:
          language: python

      - uses: cochecheee/sast-action/actions/notify-dashboard@v0.2.0
        with:
          dashboard-url:   ${{ secrets.MCP_GATEWAY_URL }}
          dashboard-token: ${{ secrets.MCP_WEBHOOK_TOKEN }}
          pipeline-status: passed
```

3 composite có sẵn:

| Action | Mục đích |
|---|---|
| `actions/sast-suite` | Run SAST tools theo language, output `reports/` |
| `actions/notify-dashboard` | POST run-metadata.json về `/webhook/pipeline-complete` |
| `actions/aggregate-sarif` | (Advanced) POST từng report file inline qua `/artifacts/process` |

---

## Workflow steps under the hood

Khi mày `uses: cochecheee/sast-action/.github/workflows/sast-ci.yml@v0.2.0`:

```
1. Checkout repo
2. actions/sast-suite (theo language input):
   - Pull semgrep image, scan → reports/semgrep.sarif
   - Trivy FS scan → reports/trivy-fs.sarif
   - + tool theo language
   - Upload artifact "sast-reports-<run_number>"
3. actions/notify-dashboard:
   - Build run-metadata.json (run_id, sha, repo, status, ...)
   - POST → ${MCP_GATEWAY_URL}/webhook/pipeline-complete
   - Output: http_status + accepted boolean
```

chat-system phía bên kia:
```
4. Webhook nhận → schedule processor.process_run()
5. Pull artifact qua GitHub API
6. Normalize SARIF/JSON → Finding schema thống nhất
7. Enrich CWE/CVSS/OWASP Top 10
8. Store DB → dashboard hiển thị
```

---

## Troubleshooting

**CI fail ở step "POST to chat-system"**:
- Check `MCP_GATEWAY_URL` secret đúng URL public, không trailing slash.
- Check chat-system instance đang up: `curl ${URL}/health`.
- `fail-on-error: 'false'` (default) thì notify fail không block CI.

**Artifact không xuất hiện trong dashboard sau 5 phút**:
- Poller mỗi 5 phút check repo → có thể trễ. Force trigger qua dashboard `/github/runs/{run_id}/reprocess`.
- Check artifact retention ≥ 5 ngày (không expire trước khi pull).
- Check `MCP_GATEWAY_URL` ở `.env` chat-system có `GITHUB_OWNER/REPO` đúng repo của bạn (single-tenant V0.1.0; multi-tenant V0.3.0).

**Java repo: Dep-Check stuck > 20 phút**:
- Cache miss đầu tháng → tải NVD ~10-15 phút (có API key) hoặc ~30 phút (không key). Đăng ký NVD_API_KEY free.
- Workflow internal đã set `nvd.api.validForHours=720` (30 ngày) — sau lần đầu rất nhanh.

**Python repo: Bandit fail "no python files"**:
- Cấu trúc repo lạ. Bandit chạy `bandit -r .` (recursive). Add `bandit.yml` để exclude folder dư.

---

## Versioning

Pin theo tag để tránh breaking change:

```yaml
uses: cochecheee/sast-action/.github/workflows/sast-ci.yml@v0.2.0
```

`@main` cũng work cho dev nhưng không stable.

Composite action cùng tag: `cochecheee/sast-action/actions/sast-suite@v0.2.0`.

---

## Limitations (v0.2.0)

1. **Single-tenant chat-system runtime** — 1 instance phục vụ 1 repo. Multi-tenant runtime ở v0.3 (foundation đã có ở v0.2 schema).
2. **Tool list cứng theo language** — chưa support custom tool list. Nếu mày muốn skip Trivy hay thêm Snyk, dùng composite trực tiếp thay reusable workflow.
3. **Chỉ GitHub Actions** — GitLab CI/Bitbucket Pipelines port-over là roadmap V0.4.
4. **`continue-on-error: true` mọi tool** — nếu 1 tool fail, các tool khác vẫn chạy. Trade-off chấp nhận để CI không block hoàn toàn.

---

## Examples

3 sample inheritor repo:
- [`cochecheee/sast-chat-sample-python`](https://github.com/cochecheee/sast-chat-sample-python) — Flask app vulnerable (SQLi, XSS, command injection sample)
- [`cochecheee/SAST_CICD`](https://github.com/cochecheee/SAST_CICD) — Java Spring (ALOUTE, original demo)
- (V0.2 sẽ thêm Node sample)

Mỗi repo có 1 workflow file < 20 dòng dùng reusable workflow này.

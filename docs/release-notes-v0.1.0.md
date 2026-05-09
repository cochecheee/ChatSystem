# chat-system v0.1.0

Đồ án tốt nghiệp — DevSecOps SAST/SCA dashboard with Vietnamese AI assistant.

First public release. Plug into any project's GitHub Actions pipeline; aggregate findings from 6 SAST tools; explain + recommend fixes via Gemini in Vietnamese; approve/revoke with audit trail; ship in two Docker containers.

> Demo target: [`cochecheee/SAST_CICD`](https://github.com/cochecheee/SAST_CICD) (Java Spring Thymeleaf, ALOUTE).

---

## Quickstart — pull and run

```bash
mkdir chat-system && cd chat-system
curl -O https://raw.githubusercontent.com/cochecheee/chat-system/v0.1.0/docker-compose.example.yml
curl -O https://raw.githubusercontent.com/cochecheee/chat-system/v0.1.0/.env.example
mv docker-compose.example.yml docker-compose.yml
mv .env.example .env
# edit .env: GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO, GEMINI_API_KEY,
#            SECRET_KEY, CI_WEBHOOK_TOKEN
docker compose up -d
open http://localhost:5173
```

Quickstart end-to-end demo: see [`docs/demo-script.md`](docs/demo-script.md).
Webhook contract for your CI: see [`docs/webhook-schema.md`](docs/webhook-schema.md).

---

## Use the composite Action in your repo

```yaml
# .github/workflows/sast.yml
- uses: cochecheee/chat-system@v0.1.0
  with:
    dashboard-url:   ${{ secrets.MCP_GATEWAY_URL }}
    dashboard-token: ${{ secrets.MCP_WEBHOOK_TOKEN }}
    pipeline-status: passed
    fail-on-error:   'false'
```

The Action POSTs the same `run-metadata.json` payload the bespoke `notify` job in the demo workflow used to emit, with retries and a 20-second timeout. Outputs `accepted` (true/false) and `http-status` for downstream steps.

---

## What changed since the redesign baseline

- 47% of UI page LOC removed (six mock-only pages cut).
- `Project` row now carries per-tenant credentials and config — runtime still single-tenant for this release; multi-tenant scaffolding lands here so the v0.2 flip-on is migration-only.
- Dependencies (SCA) tab groups Trivy CVEs by `(package, version)` with a max-fix recommendation; severity floor defaults to ≥ high so OS-CVE noise stays out of the badge math.
- Stats now expose `sast_*` and `deps_*` counts so per-tab signal matches per-tab content.
- New: webhook contract docs + per-project integration endpoint + composite Action.
- New: Docker packaging — `mcp` and `dashboard` images on Docker Hub.
- New: smoke-test script and demo collateral (script, preflight, troubleshooting).

Full diff in [`CHANGELOG.md`](CHANGELOG.md).

---

## Roadmap to v0.2

- Flip multi-tenant runtime on (`Project.list_active()` already in repo).
- Per-project AI prompt template overrides.
- DAST integration (OWASP ZAP) replacing the cut mock page.
- GitLab + Bitbucket adapters using the existing webhook contract.
- Encrypted credential storage (Fernet over `SECRET_KEY`).

---

## Acknowledgements

Tech stack: FastAPI · SQLAlchemy 2.0 · React 19 + Vite 8 · Sentinel design tokens (Inter Tight + JetBrains Mono) · Google Gemini · python-jose · detect-secrets · defusedxml · cwe2 · cvss.

Tooling under audit: Semgrep · CodeQL · SpotBugs · ESLint security plugin · Trivy · OWASP Dependency-Check.

Built with Claude Code (Opus 4.7).

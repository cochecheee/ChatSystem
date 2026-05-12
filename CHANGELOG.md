# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning per [SemVer](https://semver.org/).

## [Unreleased]

## [0.1.0] — 2026-05-15

First public release. Single-tenant SAST/SCA dashboard with a Vietnamese
AI assistant, designed to plug into a project's existing GitHub Actions
pipeline and surface findings + remediation in one place.

### Added

- **Six real dashboard pages** — Overview, Pipelines, Vulnerabilities, Dependencies (SCA), AI Chat, Reports, Settings.
- **Backend** — FastAPI + SQLAlchemy 2.0 async + aiosqlite. 200 pytest cases covering normalizer, enricher, processor, guardrails, command service, repositories, stats, integration endpoints.
- **Lenient SARIF parser** — accepts every dialect from Semgrep, CodeQL, SpotBugs, ESLint, Trivy, OWASP Dep-Check; isolates per-file errors so one malformed artifact doesn't kill the batch.
- **Per-run boards** — Pipelines tab shows each workflow run separately; reprocess endpoint to redo a single run.
- **AI guardrails** (`docs/guardrails.md`) — two-layer defense: scrubbing (detect-secrets, email/IP regex) and injection prevention (9 reject patterns + 2000-char ceiling). 24 dedicated test cases.
- **Vietnamese AI** — Gemini-backed `/explain` and `/fix` return structured 7-field JSON with Unified-Diff remediation.
- **ChatOps** — 7 slash commands (`/explain`, `/fix`, `/scan`, `/rerun`, `/approve`, `/revoke`, `/report`) with role-based access (developer / security_lead / admin) and audit trail (justification ≥ 20 chars, who/when fields per finding).
- **Free-form chat** — natural-language input maps to `suggested_command` chips when intent matches.
- **SCA grouping** — Dependencies tab groups Trivy findings by `(package, current_version)`, recommends the max fix version (semver-aware), dedups CVE per package, defaults severity floor to ≥ high.
- **Sentinel design system** — light/dark themes, Inter Tight + JetBrains Mono, warm off-white + earthy orange.
- **Webhook contract** (`docs/webhook-schema.md`) — `POST /webhook/pipeline-complete`, Bearer auth tied to `CI_WEBHOOK_TOKEN`, 202 / 403 / 422 responses, copy-paste GitHub Actions snippet.
- **Per-project integration endpoint** — `GET /projects/{id}/integration` returns webhook URL + secret names + ready-to-paste YAML step + curl test.
- **Composite GitHub Action** — `cochecheee/sast-action@v0.1.0` wraps the webhook call as a one-line workflow step with optional `fail-on-error`.
- **Multi-tenant scaffolding** — `Project` rows now carry per-tenant `github_owner/repo/token`, `gemini_api_key/model`, `artifact_profile`, `polling_workflow_name/branch`, `active`. Runtime stays single-tenant for v0.1.0; flip-on lands post-packaging.
- **Migration script** — `scripts/migrate_v2.py` adds the new columns idempotently and backfills the first row from `.env` so existing installs upgrade in place.
- **Docker packaging** — `mcp/Dockerfile` (multi-stage Python 3.13-slim, non-root, `/data` volume), `dashboard/Dockerfile` (node 20 build → nginx 1.27 serve, same-origin proxy via `nginx.conf`), `docker-compose.yml` for `up --build`, `docker-compose.example.yml` for `docker pull cochecheee/sast-chat-{mcp,dashboard}:latest`.
- **Release CI** — `.github/workflows/release.yml` builds and pushes both images to Docker Hub on `v*` tags using BuildKit gha cache.
- **Demo collateral** — `docs/demo-script.md` (15-minute walkthrough), `docs/preflight-checklist.md` (printable pre-demo checks), `docs/troubleshooting.md` (11 failure modes + fixes), `mcp/scripts/smoke_test.py` (one-shot endpoint health check).

### Changed

- Sidebar count badges removed — they invariably misled (page counts critical+high, raw count was dominated by Trivy OS-CVE noise). Bell badge for new critical/high findings since last visit kept.
- Vulnerabilities tab now hard-restricts to `category=sast`; SCA tab serves `category=deps` with grouping. Backend `/findings?category=...` filter unchanged.
- `/stats/overview` adds `sast_open`, `deps_open`, `sast_critical_high`, `deps_critical_high` so per-tab badges match per-tab content.

### Removed

- Six mock-only pages (Dast, Sca-mock, Secrets, PRBot, Governance, Repos) and `mockData.ts` — ~2,500 LOC of demo-theatre that could never be wired to real backend.
- Hardcoded `_SECURITY_ARTIFACT_NAMES` constant replaced by `mcp/config/profiles/*.yml` profiles loaded via `core/profiles.py`.
- 78 superseded planning documents from earlier phases (`.planning/phases/*`, `.planning/phase-*`); the redesign source of truth lives in `.planning/redesign/`.

### Security

- Plain-text storage of `Project.github_token` and `Project.gemini_api_key` is intentional for thesis scope. ProjectOut surfaces only `has_*` booleans — secrets never leave the server. Encryption + per-project API auth land in v0.2.

### Known limitations

- Single-tenant runtime: poller still reads `GITHUB_OWNER` / `GITHUB_REPO` from `.env`; multi-project loop scaffolded but not enabled.
- Dependencies tab is read-only — no `/upgrade` command, only the recommended-version chip + clipboard copy.
- DAST integration not shipped (was scoped to thesis V2). Roadmap doc points at OWASP ZAP.
- IEEE thesis report write-up is tracked separately and is not a v0.1.0 deliverable.

[Unreleased]: https://github.com/cochecheee/chat-system/compare/v0.1.0...HEAD
[0.1.0]:      https://github.com/cochecheee/chat-system/releases/tag/v0.1.0

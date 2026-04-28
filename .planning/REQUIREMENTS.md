# Requirements: DevSecOps SAST Dashboard

**Defined:** 2026-04-28
**Core Value:** Security findings from CI/CD pipelines — visible, understandable, and actionable within minutes of a scan completing.

## v1 Requirements

Requirements for Milestone 2 (MVP improvements). Existing MVP capabilities are Validated in PROJECT.md.

### UI/UX

- [ ] **UI-01**: User sees no intrusive toast/popup notifications; status shown via subtle inline indicators
- [ ] **UI-02**: Dashboard typography and layout follows GitHub-style design (Inter font, clean spacing, professional)
- [ ] **UI-03**: All redundant/unused UI elements removed across Overview, Vulnerabilities, Pipelines, Chat, Reports pages

### Pipeline Visibility

- [ ] **PIPE-01**: Pipeline page lists ALL GitHub workflow runs for the configured repo (not only SAST-tagged)
- [ ] **PIPE-02**: User can filter pipeline list by branch (main, feature branches, pull requests)
- [ ] **PIPE-03**: In-progress runs show real-time status updates (auto-refresh or SSE) without manual page reload
- [ ] **PIPE-04**: Pipeline page shows a trend chart — pass/fail/warning count over last 30 runs
- [ ] **PIPE-05**: Each run row shows a summary card: tools executed, finding counts by severity, run duration

### Data Processing

- [ ] **DATA-01**: SARIF parser correctly extracts message, location (file + line), rule ID, and severity from all SAST tools (Semgrep, CodeQL, ESLint, SpotBugs)
- [ ] **DATA-02**: GitHub artifact downloader handles all artifact structures produced by the SAST_CICD pipeline (zip archives, nested paths, multiple files per run)
- [ ] **DATA-03**: AI analysis context includes: affected file content (fetched from GitHub), surrounding code (±10 lines), and full finding metadata

### AI Auto-Fix

- [ ] **FIX-01**: /fix command fetches the affected source file from GitHub before generating a fix
- [ ] **FIX-02**: AI generates a code patch with full file context and explains the change
- [ ] **FIX-03**: Dashboard renders a diff preview (before/after) of the proposed fix before any push action
- [ ] **FIX-04**: User can approve fix → system creates a PR branch and pushes the patched file via GitHub API

### CVE Management

- [ ] **CVE-01**: CVE findings (from Trivy and OWASP Dep-Check) are displayed in a dedicated "Dependencies" tab, separate from code-level findings
- [ ] **CVE-02**: Main Vulnerabilities page excludes CVE findings by default (toggle to include)
- [ ] **CVE-03**: Dependencies tab shows: total CVE count, severity breakdown (Critical/High/Medium/Low), top 10 affected packages
- [ ] **CVE-04**: Each affected package shows: current version, CVE IDs, fixed version, upgrade command (e.g., `npm install package@x.y.z`)

### Chat Commands

- [ ] **CMD-01**: All 7 commands (/explain, /fix, /scan, /rerun, /approve, /revoke, /report) route correctly through CommandService
- [ ] **CMD-02**: Each command returns a structured, readable response rendered in the chat UI (not raw JSON)
- [ ] **CMD-03**: /fix command invokes the AI auto-fix flow (DATA-03 + FIX-01/02/03)
- [ ] **CMD-04**: /scan command triggers a workflow dispatch to GitHub Actions and returns run URL

## v2 Requirements

Deferred to future milestone. Not in current roadmap.

### DAST Integration

- **DAST-01**: Architecture design for integrating DAST scanner (OWASP ZAP or Nuclei) into the CI/CD pipeline
- **DAST-02**: Dashboard unified view merging SAST + DAST findings with deduplication
- **DAST-03**: DAST scan trigger from dashboard UI (authenticated endpoint scan)

### Scalability

- **SCALE-01**: Migrate from SQLite to PostgreSQL for concurrent write support
- **SCALE-02**: Extract background poller into a separate worker process (Celery or ARQ)
- **SCALE-03**: WebSocket push notifications instead of frontend polling

### Advanced AI

- **AI-01**: Cross-finding correlation — identify related vulnerabilities in the same component
- **AI-02**: Trend analysis — AI summary of security posture improvement over time
- **AI-03**: Batch auto-fix — fix multiple related findings in a single PR

## Out of Scope

| Feature | Reason |
|---------|--------|
| DAST implementation | Requires separate infra (ZAP/Nuclei); thesis scope is SAST |
| Multi-tenant / SaaS | Single repo/user scope for thesis demo |
| Database migration tooling | SQLite hand-rolled migrations acceptable for demo scale |
| Docker / CI for dashboard project | Not required for thesis deliverable |
| Auth provider overhaul (OAuth, 2FA) | Existing JWT is sufficient for demo |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| UI-01, UI-02, UI-03 | Phase 1 | Pending |
| PIPE-01 – PIPE-05 | Phase 2 | Pending |
| DATA-01, DATA-02, DATA-03 | Phase 3 | Pending |
| CVE-01 – CVE-04 | Phase 3 | Pending |
| CMD-01 – CMD-04 | Phase 4 | Pending |
| FIX-01 – FIX-04 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 22 total
- Mapped to phases: 22
- Unmapped: 0

---
*Requirements defined: 2026-04-28*
*Last updated: 2026-04-28 after initialization*

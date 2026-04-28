# DevSecOps SAST Dashboard

## What This Is

A web dashboard that integrates with GitHub Actions CI/CD pipelines to collect, normalize, and visualize SAST security findings. It polls GitHub Actions for workflow runs, fetches SARIF/XML/JSON scan artifacts from tools like Semgrep, CodeQL, OWASP Dependency-Check, and Trivy, stores findings in SQLite, and presents them through a React UI with Gemini AI-powered analysis and ChatOps commands. Built as a graduation thesis (đồ án tốt nghiệp) demo targeting the repo https://github.com/cochecheee/SAST_CICD/.

## Core Value

Security findings from CI/CD pipelines — visible, understandable, and actionable within minutes of a scan completing.

## Requirements

### Validated

- ✓ GitHub Actions polling (every 5 min) + webhook integration — MVP
- ✓ SARIF/XML/JSON artifact normalization with CWE/CVSS/OWASP enrichment — MVP
- ✓ JWT auth with 3-role RBAC (developer / security_lead / admin) — MVP
- ✓ React dashboard: Overview, Vulnerabilities, Pipelines, Chat, Reports pages — MVP
- ✓ Gemini AI analysis per finding (LLMAnalysisService) — MVP
- ✓ 7 ChatOps commands (/explain, /fix, /scan, /rerun, /approve, /revoke, /report) — MVP
- ✓ PII/secret scrubbing + prompt injection guardrails — MVP
- ✓ HTML report generation — MVP
- ✓ Finding deduplication via SHA-256 — MVP
- ✓ Finding lifecycle: pending_review → ai_analyzed → APPROVED/REVOKED — MVP

### Active

**UI/UX Overhaul**
- [ ] **UI-01**: Remove intrusive toast/popup notifications; replace with subtle inline status indicators
- [ ] **UI-02**: Redesign typography and visual hierarchy to GitHub-style (clean, readable, professional)
- [ ] **UI-03**: Audit and remove redundant/unused UI elements from all pages

**Pipeline Page**
- [ ] **PIPE-01**: Show all GitHub workflow runs (not only SAST-tagged ones)
- [ ] **PIPE-02**: Filter pipeline list by branch (main, feature, PR)
- [ ] **PIPE-03**: Real-time run status updates (polling or SSE) for in-progress runs
- [ ] **PIPE-04**: Run history trend chart (pass/fail/warning over time)
- [ ] **PIPE-05**: Per-run summary card: tools run, finding counts by severity, duration

**Data Processing**
- [ ] **DATA-01**: Fix SARIF parser to capture all required fields (message, location, rule, severity)
- [ ] **DATA-02**: Fix GitHub artifact download to handle all artifact structures from SAST_CICD repo
- [ ] **DATA-03**: Enrich AI context: include file content + surrounding code when sending findings to Gemini

**AI Auto-Fix**
- [ ] **FIX-01**: CommandService reads affected source file from GitHub before generating fix
- [ ] **FIX-02**: AI generates a patch/fix for the finding with full code context
- [ ] **FIX-03**: Dashboard shows diff preview of proposed fix before push
- [ ] **FIX-04**: Auto-push fix as a PR branch to GitHub (via GitHub API)

**CVE Management**
- [ ] **CVE-01**: Move CVE findings (Trivy / OWASP Dep-Check) into a dedicated "Dependencies" tab
- [ ] **CVE-02**: Main Vulnerabilities page filters out CVE findings by default
- [ ] **CVE-03**: Dependencies tab shows: total CVE count, severity breakdown, top affected packages
- [ ] **CVE-04**: Per-package upgrade suggestion showing current vs. fixed version

**Chat Commands Fix**
- [ ] **CMD-01**: Audit all 7 chat commands end-to-end; fix broken routing/parsing in CommandService
- [ ] **CMD-02**: Commands return structured, readable responses in the chat UI
- [ ] **CMD-03**: /fix command uses AI auto-fix flow (DATA-03, FIX-01/02)

### Out of Scope

- DAST implementation — roadmap/architecture suggestion only; full integration is a future milestone
- Multi-tenant / SaaS deployment — single-user/team demo scope
- Database migration tooling (Alembic) — SQLite hand-rolled migrations acceptable for thesis
- Real-time WebSocket push from backend — polling acceptable for demo scale
- Docker / CI pipeline for the dashboard project itself — out of thesis scope

## Context

- **Repo under analysis**: https://github.com/cochecheee/SAST_CICD/ — SAST pipeline with Semgrep, CodeQL, ESLint, SpotBugs, OWASP Dep-Check, Trivy
- **Tech stack**: Python 3.13 / FastAPI backend (`mcp/`) + React 19 / TypeScript / Vite frontend (`dashboard/`)
- **Storage**: SQLite + SQLAlchemy 2.0 async — single file, adequate for thesis demo
- **AI**: Google Gemini `gemini-3.1-pro-preview` via `google-genai` SDK
- **Background poller**: asyncio task inside FastAPI process (no separate worker) — polling every 5 min
- **Thesis context**: Demo for graduation committee; design quality and feature completeness both matter
- **Known pain points from MVP**: UI noisy, pipeline page incomplete, SARIF parse gaps, CVE noise overwhelms findings, chat commands broken, AI fix lacks source code context

## Constraints

- **Tech — SQLite**: Single-file DB; concurrent writes limited — acceptable for demo, not production
- **Tech — In-process poller**: Poller and API share one process; long polls can block API under load
- **GitHub API rate limits**: Unauthenticated: 60 req/h; token: 5000 req/h — polling interval must respect this
- **AI cost**: Gemini API calls per finding — avoid unbounded re-analysis loops
- **Thesis deadline**: Demo-ready quality is the hard constraint; extensible architecture is secondary

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| GitHub-style UI | User preference; familiar to developers; clean without dark-mode overhead | — Pending |
| CVE in dedicated tab | CVE noise drowns code-level findings; separate tab keeps main view focused | — Pending |
| AI auto-fix as PR branch | Avoids direct push to main; lets developer review before merge | — Pending |
| DAST as roadmap only | Thesis scope is SAST; DAST integration needs separate infra (ZAP/Nuclei) | — Pending |
| SQLite retained | Replacing DB is out of scope; focus on query/index improvements instead | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-28 after initialization*

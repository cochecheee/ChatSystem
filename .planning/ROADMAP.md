# Roadmap: DevSecOps SAST Dashboard

## Overview

Milestone 2 — MVP Hardening & Feature Completion. Fix all known MVP issues and deliver a demo-ready, extensible DevSecOps dashboard that supports SAST CI/CD pipelines for the SAST_CICD GitHub repository.

## Phases

- [x] **Phase 1: UI/UX Overhaul** - Replace noisy UI with clean GitHub-style design system
- [x] **Phase 2: Pipeline Visibility** - Full pipeline coverage with real-time status and trend charts (complete 2026-04-29)
- [ ] **Phase 3: Data Pipeline Fix + CVE Isolation** - Fix SARIF parsing, enrich AI context, isolate CVE findings
- [ ] **Phase 4: AI Auto-Fix + Chat Commands** - AI-driven fix pipeline and repair all chat commands
- [ ] **Phase 5: DAST Roadmap + Polish** - DAST architecture doc and demo preparation

## Phase Details

### Phase 1: UI/UX Overhaul
**Goal**: Replace noisy, inconsistent UI with a clean GitHub-style design system across all pages
**Depends on**: Nothing (first phase)
**Requirements**: UI-01, UI-02, UI-03
**Success Criteria** (what must be TRUE):
  1. No toast/popup notifications appear on any page
  2. All 5 pages use consistent Inter font, GitHub-style spacing and color tokens
  3. No dead/unused UI components visible to user
**Plans**: 2 plans

Plans:
- [x] 01-01: Design system foundation — tokens, reusable components, remove toast notifications
- [x] 01-02: Page cleanup pass — audit and remove redundant elements, standardize layouts

### Phase 2: Pipeline Visibility
**Goal**: Pipeline page shows all GitHub workflow runs with real-time status, branch filtering, trend charts, and per-run summaries
**Depends on**: Phase 1
**Requirements**: PIPE-01, PIPE-02, PIPE-03, PIPE-04, PIPE-05
**Success Criteria** (what must be TRUE):
  1. All runs from GitHub Actions appear in pipeline list (not only SAST-tagged)
  2. Branch filter narrows list correctly
  3. In-progress run status updates without manual reload
  4. Trend chart visible with at least 2 data points
  5. Each run row shows tool summary and finding counts
**Plans**: 3 plans

Plans:
- [x] 02-01-PLAN.md — Backend status fix, client.ts signature, WorkflowRun type, Wave 0 tests
- [x] 02-02-PLAN.md — Frontend branch filter, RunSummaryStrip, English copy, KPI font fix
- [x] 02-03-PLAN.md — TrendCard (AreaTrend) and LiveIndicator in Pipelines.tsx

### Phase 3: Data Pipeline Fix + CVE Isolation
**Goal**: Fix SARIF/artifact parsing so all findings have full data; isolate CVE noise into a dedicated Dependencies tab
**Depends on**: Phase 1
**Requirements**: DATA-01, DATA-02, DATA-03, CVE-01, CVE-02, CVE-03, CVE-04
**Success Criteria** (what must be TRUE):
  1. All findings from SAST_CICD artifacts have message, file, line, severity populated
  2. AI analysis prompts include affected file code snippet
  3. Dependencies tab shows CVE summary with upgrade suggestions
  4. Main Vulnerabilities page hides CVEs by default
**Plans**: 3 plans

Plans:
- [ ] 03-01-PLAN.md — SARIF relatedLocations fallback, DepCheck version fields, fixture-based tests (DATA-01, DATA-02)
- [ ] 03-02-PLAN.md — GitHubClient.fetch_file_content, LLMAnalysisService source enrichment with scrubbing (DATA-03)
- [ ] 03-03-PLAN.md — CveSummaryPanel, upgradeCmd helper, upgrade chip in dep row (CVE-01, CVE-02, CVE-03, CVE-04)

### Phase 4: AI Auto-Fix + Chat Commands
**Goal**: Repair all 7 chat commands; implement full AI auto-fix pipeline (read code → generate patch → preview diff → push PR)
**Depends on**: Phase 3
**Requirements**: CMD-01, CMD-02, CMD-03, CMD-04, FIX-01, FIX-02, FIX-03, FIX-04
**Success Criteria** (what must be TRUE):
  1. All 7 commands execute without 500 errors and return readable responses
  2. /fix command generates a code patch with source context
  3. Diff preview renders in dashboard before push
  4. Approved fix creates a PR branch on GitHub
**Plans**: 3 plans

Plans:
- [ ] 04-01: Chat command audit and repair
- [ ] 04-02: AI auto-fix pipeline (AutoFixService + patch endpoints)
- [ ] 04-03: Diff preview UI and PR push integration

### Phase 5: DAST Roadmap + Polish
**Goal**: Produce DAST integration architecture document; apply final demo polish
**Depends on**: Phase 3
**Requirements**: None (v2 suggestions only)
**Success Criteria** (what must be TRUE):
  1. DAST architecture document written with pipeline design and dashboard integration approach
  2. Full demo flow executes without errors
  3. README updated with current architecture
**Plans**: 2 plans

Plans:
- [ ] 05-01: DAST integration architecture research and documentation
- [ ] 05-02: Demo polish — smoke test, demo script, README update

## Progress

**Execution Order:** 1 → 2 and 3 (parallel) → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. UI/UX Overhaul | 2/2 | Complete | 2026-04-28 |
| 2. Pipeline Visibility | 0/3 | Planned | - |
| 3. Data Pipeline Fix + CVE Isolation | 0/3 | Planned | - |
| 4. AI Auto-Fix + Chat Commands | 0/3 | Not started | - |
| 5. DAST Roadmap + Polish | 0/2 | Not started | - |

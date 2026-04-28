# Roadmap: DevSecOps SAST Dashboard — Milestone 2

**Project:** DevSecOps SAST Dashboard
**Milestone:** M2 — MVP Hardening & Feature Completion
**Goal:** Fix all known MVP issues; deliver a demo-ready, extensible DevSecOps dashboard
**Created:** 2026-04-28

---

## Phase 1 — UI/UX Overhaul

**Goal:** Replace noisy, inconsistent UI with a clean GitHub-style design system across all pages.

**Why first:** Visible immediately on launch; sets design baseline for all subsequent feature work.

**Requirements covered:** UI-01, UI-02, UI-03

### Plans

#### 1.1 — Design System Foundation
- Install and configure Inter font; define CSS variables for GitHub-style color palette (light theme: grey-100–900, blue-600 accent, red for critical, yellow for high, green for success)
- Create reusable `Badge`, `StatusDot`, `Card`, `Button`, `Tooltip` components replacing ad-hoc inline styles
- Remove all `react-hot-toast` / notification popup calls; replace with inline `AlertBanner` component (dismissible, no auto-pop)

#### 1.2 — Page Cleanup Pass
- Audit each page (Overview, Vulnerabilities, Pipelines, Chat, Reports) and remove unused components, dead imports, and duplicate state
- Standardize page layout: consistent `PageHeader`, `SectionTitle`, spacing/padding tokens
- Fix Sidebar: remove unused nav items; ensure active state highlights correctly

**Success criteria:**
- [ ] No toast/popup notifications on any page
- [ ] Consistent font, spacing, and color on all 5 pages
- [ ] No dead/unused UI components visible to user

---

## Phase 2 — Pipeline Page Full Coverage

**Goal:** Pipeline page shows all GitHub workflow runs with real-time status, branch filtering, trend charts, and per-run summaries.

**Why second:** High-visibility feature for demo; depends on backend GitHub client (already exists) and clean UI foundation from Phase 1.

**Requirements covered:** PIPE-01, PIPE-02, PIPE-03, PIPE-04, PIPE-05

### Plans

#### 2.1 — Backend: All Runs Endpoint
- Extend `/github/runs` endpoint to return all workflow runs (not just runs with processed artifacts)
- Add query params: `branch`, `status`, `per_page`, `page`
- Return fields: `run_id`, `name`, `branch`, `status`, `conclusion`, `created_at`, `duration_seconds`, `html_url`, `tool_summary` (finding counts if processed, else null)

#### 2.2 — Frontend: Pipeline List + Filters
- Rewrite `PipelinesPage` to call new endpoint with `branch` and `status` filters
- Add `BranchFilter` dropdown (fetches branches from GitHub API via backend proxy)
- Add `StatusFilter` tabs: All / Running / Success / Failure
- `RunRow` component: shows run name, branch badge, status icon, duration, finding summary chip

#### 2.3 — Real-time Status + Trend Chart
- Add 15-second auto-refresh for in-progress runs (poll endpoint, highlight changed rows)
- Add `TrendChart` (recharts LineChart): last 30 runs, lines for critical/high/passed counts
- Add run detail slide-over panel: shows tool breakdown, artifact list, finding counts per tool

**Success criteria:**
- [ ] All runs from GitHub Actions appear in pipeline list
- [ ] Branch filter narrows list correctly
- [ ] In-progress run status updates without manual reload
- [ ] Trend chart visible with ≥2 data points

---

## Phase 3 — Data Pipeline Fix + CVE Isolation

**Goal:** Fix SARIF/artifact parsing so findings have full data; isolate CVE noise into a dedicated Dependencies tab.

**Why third:** Broken data means broken AI analysis and broken UI display. Must fix before AI auto-fix (Phase 4) can work.

**Requirements covered:** DATA-01, DATA-02, DATA-03, CVE-01, CVE-02, CVE-03, CVE-04

### Plans

#### 3.1 — SARIF & Artifact Parser Fixes
- Audit `NormalizerFactory` against actual artifacts produced by SAST_CICD pipeline (download and inspect each tool's output)
- Fix SARIF normalizer: handle `results[].message.text` vs `results[].message.markdown`; handle missing `locations`
- Fix XML normalizer (SpotBugs): parse `BugInstance` correctly including `SourceLine`
- Fix artifact downloader: handle zip-in-zip, multiple SARIF files per artifact, `content-encoding: gzip`
- Add normalizer tests using real fixture files from SAST_CICD

#### 3.2 — AI Context Enrichment
- In `LLMAnalysisService.build_prompt()`: fetch affected file from GitHub (`GET /repos/{owner}/{repo}/contents/{path}?ref={sha}`) and include ±10 lines of context
- Cache file fetches by `(sha, path)` in-memory to avoid re-fetching for multiple findings in same run
- Update prompt template to include: file name, full code snippet, finding location highlighted

#### 3.3 — CVE Tab + Dependencies View
- Add `finding_type` field to `Finding` model: `code` | `dependency`
- Triage `source_tool` in processor: Trivy and OWASP Dep-Check findings → `dependency`; others → `code`
- Create `DependenciesPage` tab in dashboard:
  - Summary row: total CVEs, Critical/High/Medium/Low counts
  - Package table: package name, current version, CVE IDs (linked), fixed version, upgrade command
- Vulnerabilities page: default filter excludes `dependency` type; add toggle "Include CVEs"

**Success criteria:**
- [ ] All findings from SAST_CICD artifacts have message, file, line, severity populated
- [ ] AI analysis includes code snippet in prompt
- [ ] Dependencies tab shows CVE summary with upgrade suggestions
- [ ] Main Vulnerabilities page hides CVEs by default

---

## Phase 4 — AI Auto-Fix + Chat Commands

**Goal:** Fix all 7 chat commands; implement full AI auto-fix flow (read code → generate patch → preview diff → push PR).

**Why fourth:** Depends on DATA-03 (code context enrichment) being in place from Phase 3.

**Requirements covered:** CMD-01, CMD-02, CMD-03, CMD-04, FIX-01, FIX-02, FIX-03, FIX-04

### Plans

#### 4.1 — Chat Command Audit & Repair
- Trace each command through `CommandService` end-to-end; document where each one breaks
- Fix command parser: handle case-insensitive commands, extra whitespace, quoted arguments
- Ensure all commands return structured `CommandResult` with `status`, `message`, `data` fields
- Fix chat UI rendering: display `CommandResult.data` as formatted cards (not raw JSON)

#### 4.2 — AI Auto-Fix Pipeline
- Implement `AutoFixService`:
  1. Fetch file content from GitHub at run SHA
  2. Build fix prompt: finding metadata + full file content + instruction to produce a minimal patch
  3. Parse Gemini response: extract patched file content + explanation
  4. Store as `Patch` record: `finding_id`, `original_content`, `patched_content`, `explanation`, `status: draft`
- Add `GET /findings/{id}/patch` and `POST /findings/{id}/patch` endpoints

#### 4.3 — Diff Preview + PR Push
- Dashboard: finding detail panel shows "Fix with AI" button → calls patch endpoint → renders diff view (`react-diff-viewer`)
- "Approve & Push" button: calls `POST /findings/{id}/patch/push`
  - Backend: creates branch `fix/finding-{id}` via GitHub API, commits patched file, opens PR
  - Returns PR URL; chat UI and finding panel display PR link

**Success criteria:**
- [ ] All 7 commands execute without 500 errors and return readable responses
- [ ] /fix command generates a patch with code context
- [ ] Diff preview renders in dashboard before push
- [ ] Approved fix creates a PR branch on GitHub

---

## Phase 5 — DAST Roadmap + Polish

**Goal:** Produce DAST integration architecture document; apply final polish and demo preparation.

**Why last:** Discovery/documentation work; no blocking dependencies. Thesis deliverable.

**Requirements covered:** DAST suggestions (v2), thesis demo readiness

### Plans

#### 5.1 — DAST Integration Architecture
- Research OWASP ZAP and Nuclei integration patterns with GitHub Actions
- Write `docs/DAST-INTEGRATION.md`: proposed pipeline stages, findings normalization approach, dashboard unified view design
- Sketch wireframe of unified SAST+DAST findings view

#### 5.2 — Demo Polish & Validation
- End-to-end smoke test: push a commit to SAST_CICD → wait for pipeline → verify findings appear → run /fix on a finding → verify PR created
- Fix any remaining UX rough edges found during smoke test
- Write `docs/DEMO-SCRIPT.md`: step-by-step demo flow for graduation committee
- Update README with setup instructions and architecture diagram

**Success criteria:**
- [ ] DAST architecture document written and reviewed
- [ ] Full demo flow executes without errors
- [ ] README updated with current architecture

---

## Phase Summary

| Phase | Focus | Key Deliverables | Req Count |
|-------|-------|-----------------|-----------|
| 1 | UI/UX Overhaul | Design system, no popups, clean pages | UI-01–03 |
| 2 | Pipeline Visibility | All runs, filters, real-time, trend chart | PIPE-01–05 |
| 3 | Data + CVE | Parser fixes, AI context, CVE tab | DATA-01–03, CVE-01–04 |
| 4 | AI Fix + Commands | Auto-fix pipeline, PR push, command repair | CMD-01–04, FIX-01–04 |
| 5 | DAST + Polish | Architecture doc, demo script | DAST suggestions |

**Total v1 requirements:** 22 across 4 execution phases

---

## Dependencies

```
Phase 1 (UI Foundation)
    └── Phase 2 (Pipeline — needs UI components)
Phase 3 (Data Fix) — independent of Phase 2, can run in parallel
    └── Phase 4 (AI Fix — needs DATA-03 for code context)
Phase 5 — independent, can start after Phase 3
```

Phases 2 and 3 can run in parallel. Phase 4 requires Phase 3 complete.

---
*Roadmap created: 2026-04-28*
*Project: DevSecOps SAST Dashboard — Milestone 2*

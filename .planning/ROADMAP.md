# Project Roadmap: Security-Integrated CI/CD System

## Phase 1: Core System Initialization ✅
- [x] Khởi tạo cấu trúc dự án (.planning/, mcp/, dashboard/).
- [x] Định nghĩa Requirements và PROJECT.md.
- [x] Thiết lập môi trường phát triển (Python venv cho mcp, npm/pnpm cho dashboard).

## Phase 2: MCP Gateway Server Development
**Plans:** 4 plans
- [x] 02-01-PLAN.md — MCP Gateway Foundation & Storage Layer
- [x] 02-02-PLAN.md — GitHub Integration & Security Guardrails
- [x] 02-03-PLAN.md — Unified Normalization & Data Enrichment (TDD)
- [x] 02-04-PLAN.md — API Integration & Workflow Wiring

## Phase 3: LLM Orchestrator Integration
**Plans:** 3 plans
- [ ] 03-01-PLAN.md — Gemini Client Integration & Mocking Infrastructure
- [ ] 03-02-PLAN.md — Prompt Engine & AI Analysis Service (Vietnamese focus)
- [ ] 03-03-PLAN.md — Response Validation & Remediation Suggestion Refinement

## Phase 4: CI/CD Pipeline & SAST Integration ✅
**Plans:** 3 plans (đã hoàn thành trên repo SAST_CICD)
- [x] 04-01-PLAN.md — Core SAST Workflow (Semgrep, CodeQL, ESLint-SARIF)
- [x] 04-02-PLAN.md — Advanced Scanners (SpotBugs SARIF, OWASP Dep-Check JSON, Trivy)
- [x] 04-03-PLAN.md — Security Gate (3 gates: SARIF threshold + SonarCloud QG + branch protection)

## Phase 5: Web Dashboard Development
**Goal:** Build the React-based security dashboard with real-time polling and integrated ChatOps panel.
**Plans:** 5 plans
- [ ] 05-01-PLAN.md — Foundation & Shadcn/UI Setup
- [ ] 05-02-PLAN.md — Findings Data & Polling
- [ ] 05-03-PLAN.md — ChatOps Interface
- [ ] 05-04-PLAN.md — Security Visualization & Pipeline Status
- [ ] 05-05-PLAN.md — Human Verification & UX Polish

## Phase 6: Advanced Dashboard Features & Final Integration
**Goal:** Implement the final advanced features and conduct E2E testing for the entire system.
**Plans:** 3 plans
- [ ] 06-01-PLAN.md — ChatOps Command Backend & Bridge Integration
- [ ] 06-02-PLAN.md — Dashboard UX (Toast Notifications & Approval UI)
- [ ] 06-03-PLAN.md — System Integration & E2E Testing

---
phase: 06-advanced-features
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - mcp/src/api/chat.py
  - dashboard/package.json
  - dashboard/src/App.tsx
  - dashboard/src/components/modals/ApprovalDialog.tsx
  - dashboard/playwright.config.ts
  - dashboard/tests/e2e/workflow.spec.ts
autonomous: true
requirements: [REQ-04-03, REQ-06-01, REQ-06-02, REQ-06-03]
must_haves:
  truths:
    - "Centralized backend parser handles ChatOps commands"
    - "Global toast notifications appear in the dashboard"
    - "Approval workflow captures justification via UI"
    - "E2E testing validates the system flow with network mocks"
  artifacts:
    - path: "mcp/src/api/chat.py"
      provides: "Backend command parser endpoint"
    - path: "dashboard/src/components/modals/ApprovalDialog.tsx"
      provides: "Approval dialog React component"
    - path: "dashboard/playwright.config.ts"
      provides: "Playwright configuration for E2E tests"
  key_links:
    - from: "dashboard/src/components/modals/ApprovalDialog.tsx"
      to: "mcp/src/api/chat.py"
      via: "API call on approval confirmation"
---

<objective>
Implement advanced features on the dashboard and conduct final integration and End-to-End testing.

Purpose: Finalize the security-integrated CI/CD system by adding command parsing, toast notifications, approval UI, and automated E2E testing.
Output: Backend command parser, integrated toast alerts, React dialog for approvals, and a configured Playwright test suite.
</objective>

<execution_context>
@D:/School/DoAnTotNghiep/chat-system/.gemini/get-shit-done/workflows/execute-plan.md
@D:/School/DoAnTotNghiep/chat-system/.gemini/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phase-6/research/RESEARCH.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Backend Command Parsing Endpoint</name>
  <files>mcp/src/api/chat.py</files>
  <action>
    - Create or update `mcp/src/api/chat.py` to implement a centralized FastAPI endpoint `POST /api/chat/command`.
    - Implement regex-based parsing to extract commands (`/explain`, `/fix`, `/approve`) and their arguments from the request payload.
    - Wire the `/approve` command to capture justification and update the database.
    - Ensure strict validation using Pydantic models for the command request.
    - Commit: `feat(phase-6): implement centralized backend command parser`
  </action>
  <verify>
    <automated>pytest mcp/tests/ -k "command"</automated>
  </verify>
  <done>Endpoint exists, validates input, and routes commands appropriately.</done>
</task>

<task type="auto">
  <name>Task 2: Frontend Toast and Approval UI</name>
  <files>dashboard/package.json, dashboard/src/App.tsx, dashboard/src/components/modals/ApprovalDialog.tsx</files>
  <action>
    - Install `sonner` in the `dashboard` directory (`npm install sonner`).
    - Integrate the `<Toaster />` at the root level in `dashboard/src/App.tsx` for global alerts.
    - Create `dashboard/src/components/modals/ApprovalDialog.tsx` utilizing Shadcn/UI Dialog components.
    - Implement a form in the dialog to capture justification when an `/approve` action is triggered.
    - Connect the dialog submission to the backend `/api/chat/command` endpoint and trigger a success toast upon completion.
    - Commit: `feat(phase-6): add sonner toasts and approval dialog UI`
  </action>
  <verify>
    <automated>npm --prefix dashboard test -- --passWithNoTests</automated>
  </verify>
  <done>Sonner is configured globally and the ApprovalDialog correctly captures and submits justification.</done>
</task>

<task type="auto">
  <name>Task 3: Playwright E2E Setup</name>
  <files>dashboard/playwright.config.ts, dashboard/tests/e2e/workflow.spec.ts</files>
  <action>
    - Install `@playwright/test` in the dashboard project (`npm install -D @playwright/test`).
    - Create `dashboard/playwright.config.ts` to configure test directories and base URLs.
    - Create `dashboard/tests/e2e/workflow.spec.ts` to implement an E2E test for the approval flow.
    - Use `page.route` to mock backend network paths (e.g. `TEST_MODE=1` for LLM orchestration) and simulate a GitHub webhook.
    - Verify the UI updates correctly based on the mock interactions.
    - Commit: `test(phase-6): setup playwright E2E testing with network mocks`
  </action>
  <verify>
    <automated>npx --prefix dashboard playwright test --project=chromium</automated>
  </verify>
  <done>Playwright is configured and the initial E2E workflow test passes using mocked network responses.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Dashboard → FastAPI | Untrusted command payloads and justifications cross this boundary. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-01 | Tampering | Backend Command Parser | mitigate | Strict input validation via Pydantic; regex validation for slash commands. |
| T-06-02 | Elevation of Privilege | Approval Workflow | mitigate | Ensure endpoint enforces authentication/role verification for `/approve`. |
</threat_model>

<verification>
1. Backend correctly parses `/explain`, `/fix`, and `/approve`.
2. Frontend displays toast notifications on command completion.
3. Approval dialog captures justification and sends it to the backend.
4. Playwright E2E test successfully runs and passes with mocked endpoints.
</verification>

<success_criteria>
- All 3 tasks are implemented and commit history reflects atomic changes.
- End-to-End flow from mock webhook to dashboard UI to approval submission is verified via automated Playwright tests.
</success_criteria>

<output>
After completion, create `.planning/phases/06-advanced-features/06-01-SUMMARY.md`
</output>
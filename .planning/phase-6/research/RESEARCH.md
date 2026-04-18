# Phase 6: Advanced Dashboard Features & Final Integration - Research

**Researched:** 2024-05-30
**Domain:** Frontend UI Components (React), E2E Testing (Playwright), Backend Command Routing (FastAPI)
**Confidence:** HIGH

## Summary

This phase focuses on the final advanced features of the dashboard and comprehensive End-to-End (E2E) testing. The core tasks involve implementing a robust command parsing mechanism (for `/explain`, `/fix`, `/approve`) bridging the frontend and backend, adding real-time toast notifications using `sonner`, creating an interactive Approval Workflow for security leads, and validating the complete system using Playwright.

**Primary recommendation:** Integrate `sonner` at the root layout for global toast notifications, implement a centralized command router in FastAPI, and use Playwright with mocked GitHub webhook endpoints for stable, deterministic E2E testing.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Create a unified `/api/chat/command` endpoint to parse and route commands (/explain, /fix, /approve, /rerun).
- D-02: Integrate the Command Parser with the LLM Orchestrator (Phase 3) for analysis-related commands.
- D-03: Implement justification capture in the `/approve` command to record reasoning in the database.
- D-04: Use **sonner** for all system-level toast notifications (new findings, command success/failure).
- D-05: Implement a **Modal/Dialog-based Approval Flow** that triggers when a user uses the `/approve` command or clicks an "Approve" button.
- D-06: Ensure the Chat Panel correctly displays status updates and system messages (e.g., "Command received", "Processing...").
- D-07: Use **Playwright** for E2E testing, targeting the full system flow from GitHub webhook simulation to Dashboard UI verification.
- D-08: Setup a dedicated test environment (SQLite DB, mock GitHub API) to ensure consistent and reliable testing.

### the agent's Discretion
- Design the toast notification styles to match the security dashboard theme.
- Choose appropriate mocking strategy for GitHub interactions in E2E tests.
- Design the justification dialog UI (Simple and clean).

### Deferred Ideas (OUT OF SCOPE)
None explicitly mentioned.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REQ-04-03 | Slash command menu with automated actions (/explain, /fix, /approve). | Command Parser pattern in FastAPI, Chat input UI updates in React. |
| REQ-06-01 | Real-time toast notifications for security findings. | Verified `sonner` library usage for global non-blocking alerts. |
| REQ-06-02 | Justification-based approval workflow for security leads. | Modal/Dialog patterns in React and state management. |
| REQ-06-03 | End-to-end system verification. | Playwright configuration and network mocking strategies. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `sonner` | 2.0.7 | Toast Notifications | Highly customizable, lightweight, and supports rich content/actions. |
| `@playwright/test` | 1.59.1 | E2E Testing | Cross-browser support, built-in auto-waiting, and excellent network mocking. |
| `lucide-react` | 1.8.0 | UI Icons | Standardized icon set with customizable stroke widths and colors. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | 9.0.2 | Backend unit tests | Testing the new `/api/chat/command` endpoint logic independently. |

**Installation:**
```bash
# Frontend
cd dashboard
npm install sonner lucide-react
npm install -D @playwright/test

# Backend E2E Test deps (if needed beyond Playwright)
cd ../mcp
pip install pytest httpx
```

## Architecture Patterns

### Command Parsing Flow
**What:** Centralized parsing of slash commands originating from the dashboard chat.
**When to use:** When users type `/explain`, `/fix`, or `/approve` in the chat input.
**Example:**
```python
# Backend FastAPI (FastAPI router pattern)
@router.post("/api/chat/command")
async def handle_command(request: CommandRequest):
    if request.command == "approve":
        return await handle_approval(request.args, request.justification)
    elif request.command == "explain":
        return await orchestrator.explain_finding(request.args)
    # ...
```

### Global Toast Notifications
**What:** Placing the `Toaster` component at the application root so any component can trigger notifications.
**Example:**
```tsx
import { Toaster, toast } from 'sonner';

function App() {
  return (
    <main>
      <YourAppComponents />
      <Toaster position="bottom-right" theme="dark" richColors />
    </main>
  );
}

// Triggering
toast.success('Action approved', { description: 'The pull request is now cleared.' });
```

### Anti-Patterns to Avoid
- **Hardcoding Webhook URLs in E2E Tests:** This makes tests brittle. Use Playwright's `page.route` to mock external API responses.
- **Scattered Command Logic:** Avoid processing commands directly inside UI components. Send the raw string or parsed command to the backend to maintain a single source of truth.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Toast Notifications | Custom floating `div` with timeouts and animation logic | `sonner` | Handles stacking, positioning, swipe-to-dismiss, and accessibility out-of-the-box. |
| Browser Automation | Raw Puppeteer or Selenium | `Playwright` | Auto-waits for elements, intercepts network natively, simpler setup. |

## Common Pitfalls

### Pitfall 1: Playwright Tests Failing on CI due to Network Latency
**What goes wrong:** Tests pass locally but timeout in CI environments.
**Why it happens:** Real APIs (like GitHub) take longer to respond, or rate-limiting kicks in.
**How to avoid:** Mock all external boundaries using `page.route('**/*github.com/**', route => ...)`.
**Warning signs:** Flaky test runs that intermittently timeout.

### Pitfall 2: Modal Focus Trapping
**What goes wrong:** Users tab out of the Justification Approval Modal into the background page.
**Why it happens:** Native HTML/React doesn't trap focus in dialogs by default unless using native `<dialog>` or a robust library.
**How to avoid:** Implement standard focus management or utilize a headless UI approach if not hand-rolling the accessible dialog wrapper.

## Code Examples

### Sonner Toast Trigger
```typescript
import { toast } from 'sonner';

export const handleApproveClick = () => {
    toast.promise(submitApproval(justification), {
        loading: 'Submitting approval...',
        success: (data) => `Approval recorded: ${data.id}`,
        error: 'Failed to submit approval',
    });
};
```

### Playwright Webhook Mocking
```typescript
import { test, expect } from '@playwright/test';

test('Simulate GitHub Webhook to Dashboard', async ({ page }) => {
  await page.route('**/api/webhook/github', async route => {
    const json = { status: 'received', pr_id: 123 };
    await route.fulfill({ json });
  });

  await page.goto('/');
  // Assert UI updates based on the webhook
});
```

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `sonner` is the preferred toast library over `react-hot-toast` or `react-toastify` based on the prompt context and constraints. | Constraints | Low - Can be swapped if another library was intended, but `sonner` is explicitly requested in D-04. |
| A2 | Playwright tests will be run against a locally served dashboard and a test-mode FastAPI backend. | Testing | Medium - Tests may interfere with actual data if not isolated. |

## Open Questions

1. **GitHub Mocking Scope:**
   - What we know: Playwright needs to mock GitHub interactions.
   - What's unclear: Should the backend also have a "test mode" to mock outbound LLM calls (e.g. to Gemini/OpenAI) during E2E tests?
   - Recommendation: Use a test environment variable (`TEST_MODE=1`) in FastAPI to bypass actual LLM calls and return static analysis results during E2E.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | Dashboard, Playwright | ✓ | v22.19.0 | — |
| npm | Dashboard, Playwright | ✓ | 10.9.3 | — |
| Python | FastAPI, Pytest | ✓ | 3.13.1 | — |
| pip | FastAPI, Pytest | ✓ | 25.3 | — |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Playwright (Frontend E2E), Pytest (Backend) |
| Config file | `playwright.config.ts` (TBD), `pytest.ini` (TBD) |
| Quick run command | `npx playwright test --ui` |
| Full suite command | `npx playwright test` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-04-03 | Command Parsing (`/explain`, `/approve`) | e2e / unit | `npx playwright test tests/commands.spec.ts` | ❌ Wave 0 |
| REQ-06-01 | Toast Notifications on actions | e2e | `npx playwright test tests/notifications.spec.ts` | ❌ Wave 0 |
| REQ-06-02 | Approval Workflow Dialog and Submission | e2e | `npx playwright test tests/approval.spec.ts` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest` (backend logic), `npx playwright test` (specific feature)
- **Per wave merge:** Full suite `npx playwright test`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `dashboard/playwright.config.ts` — configuration for local dev server + backend execution.
- [ ] `dashboard/tests/e2e/` — initialize e2e test directory.
- [ ] `mcp/tests/` — configure unit testing for command router.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Role-based verification for `/approve` |
| V3 Session Management | yes | Secure tokens for communicating with Backend |
| V4 Access Control | yes | Ensure only "Security Leads" can execute `/approve` |
| V5 Input Validation | yes | `pydantic` on FastAPI command requests |

### Known Threat Patterns for FastAPI / React Commands

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Command Injection | Tampering | Strict regex validation of command strings (`^\/[a-z]+`) and parameterized arguments. |
| Unauthorized Approval | Elevation of Privilege | Backend must verify user role/session when `/api/chat/command` (approve) is hit. |
| XSS via Toast | Tampering | React auto-escapes, but ensure `sonner` is not passed raw HTML strings if rendering user input. |

## Sources
### Primary (HIGH confidence)
- ROADMAP.md - Project milestones and phase 6 goals.
- 06-CONTEXT.md - Specific design constraints and decisions for the phase.
- `package.json` and `requirements.txt` - Project dependencies.

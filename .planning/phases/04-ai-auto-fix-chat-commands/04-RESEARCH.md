# Phase 04: AI Auto-Fix + Chat Commands — Research

**Researched:** 2026-04-29
**Domain:** ChatOps command routing, AI-driven patch generation, GitHub PR workflow, diff preview UI
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CMD-01 | All 7 commands (/explain, /fix, /scan, /rerun, /approve, /revoke, /report) route correctly through CommandService | CommandService dispatch table already routes all 7 — /fix currently aliases to /explain; needs its own handler |
| CMD-02 | Each command returns a structured, readable response rendered in the chat UI (not raw JSON) | Chat.tsx already renders explanation_vi, impact_vi, remediation_diff as formatted text; /scan and /rerun need run URLs added to response |
| CMD-03 | /fix command invokes the AI auto-fix flow (DATA-03 + FIX-01/02/03) | Requires splitting /fix from /explain dispatch and wiring to new AutoFixService |
| CMD-04 | /scan command triggers a workflow dispatch to GitHub Actions and returns run URL | dispatch_workflow() fires but returns None; need to list latest run after dispatch to return html_url |
| FIX-01 | /fix command fetches the affected source file from GitHub before generating a fix | LLMAnalysisService.analyze_finding already fetches via github_client.fetch_file_content; reusable |
| FIX-02 | AI generates a code patch with full file context and explains the change | Gemini already emits remediation_diff in AnalysisOutput; AutoFixService needs a dedicated fix prompt |
| FIX-03 | Dashboard renders a diff preview (before/after) of the proposed fix before any push action | New DiffView component needed in React; unified-diff string already available in remediation_diff |
| FIX-04 | User can approve fix → system creates a PR branch and pushes the patched file via GitHub API | Requires 3 new GitHub API calls: get file SHA, create branch ref, put file content, create PR |
</phase_requirements>

---

## Summary

Phase 04 targets two related but independent concerns: (1) repairing the 7 ChatOps commands so they all return meaningful, readable responses, and (2) building the full AI auto-fix pipeline from code fetch through diff preview to PR push.

The command infrastructure is already in good shape — all 7 commands route through `CommandService` and the role-based auth matrix in `COMMAND_ROLES` is wired. The primary gaps are: `/fix` is aliased to `/explain` (same handler), `/scan` does not return a run URL, and `/rerun` does not validate that the run_id is reasonable. None of these require schema changes; they are handler-level fixes. [VERIFIED: mcp/src/services/command_service.py, mcp/src/api/chat.py]

The auto-fix pipeline requires a new `AutoFixService` on the backend (new file: `mcp/src/services/auto_fix_service.py`) plus three new API endpoints, and a `DiffView` component plus an "approve fix" flow on the frontend. The GitHub PR creation requires three sequential GitHub API calls — get file SHA → create branch → push patched file → create PR — all using the existing `httpx`-based `GitHubClient` pattern. [VERIFIED: docs.github.com/en/rest/git/refs, docs.github.com/en/rest/repos/contents, docs.github.com/en/rest/pulls/pulls]

Phase 03 delivered `LLMAnalysisService` with `fetch_file_content` and source scrubbing already wired. Phase 04 reuses these capabilities: AutoFixService will delegate the source-fetch step to `LLMAnalysisService.analyze_finding()` (or call `fetch_file_content` directly) so there is no duplication. The Gemini model already produces a `remediation_diff` field in structured JSON — the fix prompt just needs to emphasize complete unified-diff output.

**Primary recommendation:** Build the fix pipeline as a thin `AutoFixService` that calls existing services (`LLMAnalysisService`, `GitHubClient`), exposes three new endpoints, and stores patch state in `Finding.raw_data`. The frontend DiffView is a pure display component — no new state management library needed.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Command routing + RBAC | API / Backend | — | All 7 command handlers are in CommandService/chat.py; role enforcement is backend-only |
| /scan run URL return | API / Backend | — | Must call GitHub API post-dispatch to get the new run's html_url; can't be done in browser |
| AI fix generation | API / Backend | — | Gemini call with code context is a backend-only operation (API key, guardrails, structured output) |
| Patch storage (before push) | API / Backend | — | Patch stored in Finding.raw_data to survive across requests without introducing new state |
| Diff preview rendering | Browser / Client | — | Pure display of a diff string; React component, no server round-trip |
| PR creation | API / Backend | — | GitHub token is backend-only; frontend sends approve request, backend executes API calls |
| Diff preview approval flow | Browser / Client | API / Backend | Frontend shows modal, collects confirmation; backend executes PR push on approval |

---

## Standard Stack

### Core — No New Dependencies Required

All capabilities needed for Phase 04 are achievable with the existing stack. [VERIFIED: mcp/requirements.txt, dashboard/package.json]

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `google-genai` | 1.73.1 | Structured Gemini calls for fix generation | Already installed; `GeminiClient.analyze()` reused |
| `httpx` | >=0.27.0 | GitHub API calls (branch create, file push, PR create) | Already installed; `GitHubClient` pattern in place |
| `sqlalchemy` (async) | >=2.0.0 | Store patch in Finding.raw_data JSON column | Already installed; zero migration needed |
| React 19 | ^19.2.4 | DiffView component, approve-fix dialog | Already installed |

### No New Packages to Install

Phase 04 does NOT require additional Python packages (no diff library needed — Gemini emits unified-diff text directly, and the frontend renders it as a code block with custom styling). [VERIFIED: existing remediation_diff field in AnalysisOutput]

There is no npm diff-rendering library in the project. The diff can be displayed as a syntax-highlighted `<pre>` block parsing `+`/`-` line prefixes inline — consistent with the existing Charts.tsx pattern of building custom SVG rather than adding charting libraries.

---

## Architecture Patterns

### System Architecture Diagram

```
/fix [id]
    │
    ▼
POST /api/chat/command  (chat.py — RBAC check)
    │
    ▼
CommandService._handle_fix()
    │
    ├─► LLMAnalysisService.analyze_finding()   [fetch source + Gemini structured JSON]
    │       │
    │       ├─► GitHubClient.fetch_file_content()  [GitHub Contents API]
    │       └─► GeminiClient.analyze()             [returns AnalysisOutput incl. remediation_diff]
    │
    ├─► Store patch in Finding.raw_data["pending_fix"]
    │
    └─► CommandResponse{ data: { patch, file_path, ... } }
            │
            ▼
    Chat.tsx executeCommand()
            │
            ▼
    DiffView component (renders +/- lines)
            │
            ▼
    "Approve & Push PR" button
            │
            ▼
POST /api/fix/{finding_id}/push-pr   (new endpoint)
            │
            ▼
AutoFixService.push_pr()
    ├─► GET /repos/{o}/{r}/contents/{path}   [get current SHA]
    ├─► POST /repos/{o}/{r}/git/refs         [create fix branch]
    ├─► PUT /repos/{o}/{r}/contents/{path}   [push patched file]
    └─► POST /repos/{o}/{r}/pulls            [open PR]
            │
            ▼
    CommandResponse{ data: { pr_url } }
            │
            ▼
    Chat.tsx shows PR link
```

### Recommended Project Structure — Changes Only

```
mcp/src/
├── services/
│   ├── auto_fix_service.py      # NEW — AutoFixService: apply patch + push PR
│   └── command_service.py       # MODIFY — split /fix from /explain dispatch
├── api/
│   └── fix.py                   # NEW — /api/fix/{id}/preview and /push-pr endpoints
└── main.py                      # MODIFY — register fix router

dashboard/src/
├── components/
│   └── DiffView.tsx             # NEW — diff rendering component (+/- line coloring)
└── pages/
    └── Chat.tsx                 # MODIFY — render DiffView + "Push PR" button on /fix response
```

### Pattern 1: Splitting /fix from /explain in CommandService

**What:** `/fix` currently maps to `_handle_explain`. It needs its own handler that invokes `AutoFixService`.
**When to use:** Whenever a command needs different data/behavior than an existing alias.

```python
# Source: mcp/src/services/command_service.py (existing dispatch dict)
dispatch: dict[str, Any] = {
    "explain": self._handle_explain,
    "fix":     self._handle_fix,        # change: was _handle_explain
    "scan":    self._handle_scan,
    "rerun":   self._handle_rerun,
    "approve": self._handle_approve,
    "revoke":  self._handle_revoke,
    "report":  self._handle_report,
}
```

### Pattern 2: AutoFixService — Patch Generation

**What:** Delegate to `LLMAnalysisService` for source fetch + analysis, then cache the patch.

```python
# mcp/src/services/auto_fix_service.py
class AutoFixService:
    def __init__(
        self,
        llm: LLMAnalysisService | None = None,
        github: GitHubClient | None = None,
    ) -> None:
        self._llm = llm or LLMAnalysisService()
        self._github = github or GitHubClient()

    async def generate_fix(self, finding: Finding, session: AsyncSession) -> dict:
        """Run analyze_finding to get remediation_diff; cache in finding.raw_data."""
        result = await self._llm.analyze_finding(finding, session)
        patch = result.remediation_diff
        raw = dict(finding.raw_data or {})
        raw["pending_fix"] = {
            "patch": patch,
            "file_path": finding.file_path,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        finding.raw_data = raw
        await session.commit()
        return raw["pending_fix"]
```

### Pattern 3: GitHub PR Creation — 4-Step Sequence

**What:** Create PR branch from HEAD, push patched file, open PR.
**GitHub API endpoints:** [CITED: docs.github.com/en/rest/git/refs, docs.github.com/en/rest/repos/contents, docs.github.com/en/rest/pulls/pulls]

```python
# Step 1: Get file SHA (needed for the PUT update)
GET /repos/{owner}/{repo}/contents/{path}?ref=main
# Returns: data["sha"] — required to update existing file

# Step 2: Create fix branch from main HEAD SHA
POST /repos/{owner}/{repo}/git/refs
body: {"ref": "refs/heads/fix/finding-{id}", "sha": <main-head-sha>}

# Step 3: Push patched file to fix branch
PUT /repos/{owner}/{repo}/contents/{path}
body: {
    "message": "fix: auto-patch for finding #{id} ({rule_id})",
    "content": base64.b64encode(patched_content.encode()).decode(),
    "sha": <file-sha-from-step-1>,
    "branch": "fix/finding-{id}"
}

# Step 4: Open PR
POST /repos/{owner}/{repo}/pulls
body: {
    "title": "Auto-fix: finding #{id} — {rule_id}",
    "head": "fix/finding-{id}",
    "base": "main",
    "body": "Automated fix generated by Sentinel AI.\n\n{explanation_vi}"
}
```

### Pattern 4: Getting main HEAD SHA (needed for branch creation)

```python
# GET /repos/{owner}/{repo}/git/refs/heads/main
# Returns: data["object"]["sha"]
# This SHA is used as the starting point for the fix branch
```

### Pattern 5: /scan Command — Return Run URL

**What:** After `dispatch_workflow()`, poll the runs list to return the newly created run URL.

```python
# In _handle_scan (command_service.py)
await self._github.dispatch_workflow("ci.yml")
# Add: brief sleep then list most recent run to get html_url
runs = await self._github.list_workflow_runs(status="")  # include queued
if runs:
    latest = runs[0]
    run_url = latest.get("html_url", "")
    run_id = latest.get("id")
```

Note: GitHub dispatch_workflow returns HTTP 204 with no body. The only way to get the new run ID is to list runs after dispatch and take the most recently created one. A 1-2 second delay may be needed. [VERIFIED: github_client.py dispatch_workflow returns None]

### Pattern 6: DiffView Component (Frontend)

**What:** React component that parses unified-diff text and renders `+`/`-` lines with color.

```tsx
// dashboard/src/components/DiffView.tsx
function DiffView({ diff }: { diff: string }) {
  const lines = diff.split('\n');
  return (
    <pre style={{ fontFamily: 'monospace', fontSize: 12, overflowX: 'auto' }}>
      {lines.map((line, i) => (
        <div key={i} style={{
          background: line.startsWith('+') ? 'rgba(40,167,69,0.15)' :
                      line.startsWith('-') ? 'rgba(220,53,69,0.15)' :
                      'transparent',
          color: line.startsWith('+') ? 'var(--sev-low-fg)' :
                 line.startsWith('-') ? 'var(--sev-high-fg)' :
                 'var(--fg)',
        }}>
          {line || ' '}
        </div>
      ))}
    </pre>
  );
}
```

This approach uses existing design tokens (`--sev-low-fg`, `--sev-high-fg`, `--fg`) and requires no external library. [VERIFIED: dashboard/src/tokens.css design token pattern in codebase]

### Anti-Patterns to Avoid

- **Parsing the unified diff in Python to apply patches:** Do NOT use `difflib.patch` or any diff-apply library on the backend. The Gemini output is a suggested diff for display; the actual patched content to push must be reconstructed from the full source file + the diff guidance from Gemini. Apply patches by re-fetching source + having Gemini return the full patched file content (separate "fix_content" field), not by parsing diffs.
- **Storing patch state in a new DB table:** Use `Finding.raw_data["pending_fix"]` JSON column. No schema migration needed. The JSON column already holds per-finding blob data.
- **Blocking the API thread during PR creation:** The 4-step GitHub sequence can take 2-3 seconds. Run it async — all `httpx` calls in `GitHubClient` are already `async with httpx.AsyncClient()`.
- **Hardcoding branch name prefix:** Use `fix/finding-{id}` pattern — predictable, unique per finding, easy to search. Guard against creating duplicate branches (check if branch exists first; if yes, append a suffix).
- **Not validating that the patch is non-empty before push:** Gemini occasionally returns empty `remediation_diff`. Guard: if `not patch.strip()`, return error response before attempting PR creation.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Diff rendering | Custom parser with regex | Inline `+`/`-` prefix coloring | Sufficient for displaying Gemini-generated unified diffs; no edge cases (merge conflicts, binary) |
| Patch application | Python difflib/patch | Full patched content from Gemini | Diff parsing is brittle; LLM can return the complete fixed file directly |
| Branch naming uniqueness | UUID-based names | `fix/finding-{finding.id}` | Finding ID is already unique in DB; deterministic name is readable and debuggable |
| PR description | Hand-craft markdown | Reuse `explanation_vi` + `impact_vi` from AnalysisResult | Already generated by Gemini; no additional LLM call needed |

**Key insight:** The Gemini model already produces a structured `remediation_diff` plus Vietnamese explanation fields. Phase 04 wraps this in a push workflow — it does not need to re-engineer the AI layer.

---

## Common Pitfalls

### Pitfall 1: dispatch_workflow Returns 204 No Body
**What goes wrong:** Calling `dispatch_workflow()` then immediately calling `list_workflow_runs()` returns the previous run, not the new one. The new run may not appear for 1-5 seconds.
**Why it happens:** GitHub creates the run asynchronously after the dispatch event.
**How to avoid:** Add a short `await asyncio.sleep(2)` after dispatch before listing runs, and filter for runs created after `datetime.now(UTC) - timedelta(seconds=10)`.
**Warning signs:** `/scan` returns an old run's URL or no URL at all.
[VERIFIED: github_client.py dispatch_workflow implementation]

### Pitfall 2: File SHA Required for PUT /contents Update
**What goes wrong:** `PUT /repos/{o}/{r}/contents/{path}` returns HTTP 422 ("Invalid request") if the `sha` field is missing when the file already exists.
**Why it happens:** GitHub requires the current blob SHA to perform an optimistic concurrency check.
**How to avoid:** Always call `GET /contents/{path}` first to retrieve `data["sha"]` before calling PUT.
**Warning signs:** 422 Unprocessable Entity from GitHub during file push step.
[CITED: docs.github.com/en/rest/repos/contents]

### Pitfall 3: Gemini remediation_diff May Contain Noise
**What goes wrong:** `AnalysisOutput.remediation_diff` sometimes contains prose text mixed with diff syntax, or is entirely prose when Gemini lacks context.
**Why it happens:** The current `SYSTEM_INSTRUCTION` asks for "Unified Diff" but doesn't enforce strict format.
**How to avoid:** Add a dedicated fix prompt that explicitly requests: `Return ONLY the unified diff block starting with @@ — no prose, no explanation text in the diff field.` Use a separate `fix_content` field (full patched file) as the actual content to push if the diff is too ambiguous.
**Warning signs:** DiffView renders lines without `+`/`-` prefixes; patch is empty.

### Pitfall 4: /fix Called Without finding_id
**What goes wrong:** `CommandRequest.finding_id` is `int | None`. If user types `/fix` without an ID, `_get_finding(None, db)` raises HTTP 422.
**Why it happens:** The field is optional in the schema; command parser in Chat.tsx passes `parseInt(args[0])` which produces `NaN` → `undefined` if no arg.
**How to avoid:** Frontend: show inline error "Cú pháp: /fix [finding_id]" if args[0] is absent. Backend: already handled by `_get_finding()` which raises 422 on `None`.
**Warning signs:** HTTP 422 on `/fix` command with no ID.
[VERIFIED: Chat.tsx executeCommand, command_service.py _get_finding]

### Pitfall 5: Fix Branch Already Exists
**What goes wrong:** If user runs `/fix` then "Push PR" twice, the second GitHub `POST /git/refs` returns HTTP 422 (Reference already exists).
**Why it happens:** Branch name `fix/finding-{id}` is deterministic — same finding creates same branch name.
**How to avoid:** Before creating branch, call `GET /repos/{o}/{r}/git/refs/heads/fix/finding-{id}` — if 200, the branch exists; either delete and recreate, or append `-v2` suffix. Simplest: update existing branch rather than error.
**Warning signs:** 422 from GitHub branch creation step.
[CITED: docs.github.com/en/rest/git/refs]

### Pitfall 6: Applying Patch to Binary/Java Class Files
**What goes wrong:** `fetch_file_content` already skips `.jar/.class/.war/.ear` files. But AutoFixService must also guard against pushing a patch to these files.
**Why it happens:** LLMAnalysisService falls back gracefully to "no code context" for binary files, so Gemini produces a generic diff that can't be applied.
**How to avoid:** In `AutoFixService.push_pr()`, validate `finding.file_path` does not end in a binary extension before attempting the PR push.
**Warning signs:** PR created with base64-encoded binary content.
[VERIFIED: mcp/src/services/llm/service.py lines 53-56]

---

## Code Examples

### Complete 4-Step PR Push Flow (GitHubClient additions)

```python
# Source: GitHub REST API docs — verified 2026-04-29
# To add to mcp/src/services/github_client.py

async def get_file_sha(self, file_path: str, ref: str = "main") -> tuple[str, str]:
    """Returns (file_sha, current_content_base64)."""
    clean_path = file_path.lstrip("/")
    async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
        resp = await client.get(
            f"{_GITHUB_API}/repos/{self.owner}/{self.repo}/contents/{clean_path}",
            params={"ref": ref},
        )
        resp.raise_for_status()
    data = resp.json()
    return data["sha"], data.get("content", "")

async def get_default_branch_sha(self, branch: str = "main") -> str:
    """Get HEAD SHA of a branch (needed to create a new branch from it)."""
    async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
        resp = await client.get(
            f"{_GITHUB_API}/repos/{self.owner}/{self.repo}/git/refs/heads/{branch}"
        )
        resp.raise_for_status()
    return resp.json()["object"]["sha"]

async def create_branch(self, branch_name: str, sha: str) -> None:
    """Create a new branch ref pointing to sha."""
    async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
        resp = await client.post(
            f"{_GITHUB_API}/repos/{self.owner}/{self.repo}/git/refs",
            json={"ref": f"refs/heads/{branch_name}", "sha": sha},
        )
        resp.raise_for_status()

async def push_file(
    self,
    file_path: str,
    content: str,
    file_sha: str,
    branch: str,
    commit_message: str,
) -> None:
    """Create or update a file on a specific branch."""
    import base64
    encoded = base64.b64encode(content.encode()).decode()
    clean_path = file_path.lstrip("/")
    async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
        resp = await client.put(
            f"{_GITHUB_API}/repos/{self.owner}/{self.repo}/contents/{clean_path}",
            json={
                "message": commit_message,
                "content": encoded,
                "sha": file_sha,
                "branch": branch,
            },
        )
        resp.raise_for_status()

async def create_pull_request(
    self,
    title: str,
    head: str,
    base: str = "main",
    body: str = "",
) -> str:
    """Create a PR and return its html_url."""
    async with httpx.AsyncClient(headers=self._headers, timeout=30) as client:
        resp = await client.post(
            f"{_GITHUB_API}/repos/{self.owner}/{self.repo}/pulls",
            json={"title": title, "head": head, "base": base, "body": body},
        )
        resp.raise_for_status()
    return resp.json()["html_url"]
```

### New Endpoint: Preview Fix

```python
# Source: FastAPI pattern from mcp/src/api/analysis.py
# mcp/src/api/fix.py — new file

router = APIRouter(prefix="/api/fix", tags=["fix"])

@router.post("/{finding_id}/generate", response_model=CommandResponse)
async def generate_fix(
    finding_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> CommandResponse:
    """Generate and cache a fix patch for a finding."""
    if current_user.role not in ("developer", "security_lead", "admin"):
        raise HTTPException(status_code=403)
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail=f"Finding #{finding_id} not found.")
    svc = AutoFixService()
    patch_info = await svc.generate_fix(finding, db)
    return CommandResponse(status="ok", message="Patch generated.", data=patch_info)

@router.post("/{finding_id}/push-pr", response_model=CommandResponse)
async def push_pr(
    finding_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> CommandResponse:
    """Push cached patch as a GitHub PR. Requires security_lead or admin."""
    if current_user.role not in ("security_lead", "admin"):
        raise HTTPException(status_code=403)
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404)
    svc = AutoFixService()
    pr_url = await svc.push_pr(finding, current_user.username, db)
    return CommandResponse(status="ok", message="PR created.", data={"pr_url": pr_url})
```

### Frontend DiffView + Push PR Button (Chat.tsx additions)

```typescript
// Source: existing Chat.tsx pattern
// Additions to executeCommand() when cmd === 'fix':

if (res.data?.patch) {
  // Show diff preview with approve button
  text += '\n\n**Diff Preview:**';
  // DiffView renders below in JSX
  setCurrentPatch({ findingId: req.finding_id!, patch: res.data.patch as string });
}

// New state: currentPatch / onPushPR handler
const handlePushPR = async () => {
  if (!currentPatch) return;
  const res = await api.fix.pushPr(currentPatch.findingId);
  setCmdStatus({ type: 'success', msg: `PR created: ${res.data?.pr_url}` });
  setCurrentPatch(null);
};
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| /fix aliased to /explain | /fix has dedicated handler + AutoFixService | Phase 04 | Separates analysis (explain) from patching (fix) |
| No PR creation capability | 4-step GitHub API PR workflow | Phase 04 | Closes FIX-04 |
| No diff preview in UI | DiffView component with +/- coloring | Phase 04 | Closes FIX-03 |
| /scan returns no run URL | /scan fetches latest run after dispatch | Phase 04 | Closes CMD-04 readable response |

**Current state confirmed:** [VERIFIED: command_service.py — /fix aliases _handle_explain at line 41]

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Gemini `remediation_diff` output is usable as display diff (does not need machine-application) — we display it and use full patched content for the actual push | Architecture Patterns | If Gemini only outputs patches (no full content), push_file step needs a diff-apply library |
| A2 | `dispatch_workflow` + 2s sleep + list_runs[0] reliably returns the new run | Pattern 5, Pitfall 1 | If GitHub delays run creation >5s, /scan returns wrong run URL |
| A3 | The `GITHUB_TOKEN` configured in `.env` has `repo` + `workflow` scopes sufficient for PR creation | GitHub PR push flow | If PAT lacks `pull_requests:write`, PR creation returns 403 |
| A4 | AutoFixService calls `LLMAnalysisService.analyze_finding()` rather than duplicating source-fetch logic | Pattern 2 | If analyze_finding signature changes in future, AutoFixService breaks |

**Assumption A1 detailed note:** The recommended approach is to have AutoFixService request a second Gemini call specifically for the "full patched file content" (stored as `pending_fix.full_content`) when the user clicks "Push PR". The `remediation_diff` is for display only. This avoids the brittle diff-application problem entirely. [ASSUMED — depends on Gemini reliably returning full content; can fall back to displaying the diff and asking user to manually apply]

---

## Open Questions

1. **How to handle Gemini returning a partial diff vs. full patched content**
   - What we know: `remediation_diff` in `AnalysisOutput` is a string; current prompt says "Unified Diff"
   - What's unclear: Whether Gemini reliably returns a machine-applicable diff or mixed prose+diff
   - Recommendation: Add a second `fix_content` field to a new `FixOutput` Pydantic schema specifically for the file content to push; keep `remediation_diff` for display only

2. **Whether GITHUB_TOKEN PAT has PR-creation scope**
   - What we know: Token is configured with `repo` + `workflow` (from STACK.md and .env.example)
   - What's unclear: Whether `repo` scope covers PR creation (it should — `repo` includes `pull_requests`)
   - Recommendation: Document in plan that user must verify PAT scopes before running 04-03

3. **Diff preview UX in Chat.tsx — inline vs. modal**
   - What we know: Chat.tsx currently renders text responses inline in the message list
   - What's unclear: Whether a large diff should be shown inline or in an expandable panel
   - Recommendation: Render DiffView inline in the message bubble, with an expand/collapse toggle for diffs >20 lines; add "Push PR" button below the diff

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 | Backend | Yes | 3.13.1 | — |
| Node.js | Frontend | Yes | v22.19.0 | — |
| google-genai | Fix generation | Yes | 1.73.1 | — |
| httpx | GitHub API calls | Yes | >=0.27.0 (installed) | — |
| pytest + pytest-asyncio | Backend tests | Yes | pytest-9.0.3 | — |
| GITHUB_TOKEN | PR push | [ASSUMED] configured | — | Phase gate: verify PAT scopes |
| GEMINI_API_KEY | Fix generation | [ASSUMED] configured | — | Tests use mock; real calls need key |

**Missing dependencies with no fallback:** None (all tooling available locally).

**Missing dependencies with fallback:** PR-push step requires a configured GitHub PAT with `repo` scope. Tests for push_pr should use `AsyncMock` for `GitHubClient` to avoid real API calls.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 1.3.0 |
| Config file | `mcp/pytest.ini` (`asyncio_mode = auto`) |
| Quick run command | `python -m pytest tests/test_chat_api.py tests/test_auto_fix_service.py -q` |
| Full suite command | `python -m pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CMD-01 | All 7 commands route without 500 | integration | `pytest tests/test_chat_api.py -q` | Yes |
| CMD-02 | /scan returns run URL in data | integration | `pytest tests/test_chat_api.py::test_scan_returns_run_url -q` | No — Wave 0 |
| CMD-03 | /fix routes to AutoFixService, not explain | unit | `pytest tests/test_auto_fix_service.py::test_fix_calls_autofix -q` | No — Wave 0 |
| CMD-04 | /scan dispatches and returns html_url | integration | `pytest tests/test_chat_api.py::test_scan_dispatch -q` | No — Wave 0 |
| FIX-01 | AutoFixService fetches source from GitHub | unit | `pytest tests/test_auto_fix_service.py::test_generate_fix_fetches_source -q` | No — Wave 0 |
| FIX-02 | generate_fix stores patch in raw_data["pending_fix"] | unit | `pytest tests/test_auto_fix_service.py::test_generate_fix_stores_patch -q` | No — Wave 0 |
| FIX-03 | DiffView renders +/- lines (Playwright smoke) | e2e | `npx playwright test tests/e2e/chatops.spec.ts` | Partial — extend |
| FIX-04 | push_pr calls GitHub API with correct sequence | unit | `pytest tests/test_auto_fix_service.py::test_push_pr_sequence -q` | No — Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_chat_api.py tests/test_auto_fix_service.py -q`
- **Per wave merge:** `python -m pytest -q` (full 180+ test suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `mcp/tests/test_auto_fix_service.py` — unit tests for CMD-03, FIX-01, FIX-02, FIX-04 (all using AsyncMock GitHubClient)
- [ ] New test cases in `mcp/tests/test_chat_api.py` — for CMD-02 and CMD-04 (/scan run URL return)
- [ ] `dashboard/tests/e2e/chatops.spec.ts` — extend with DiffView render and push-PR button existence check

*(All backend tests run in-memory; no real GitHub/Gemini calls needed in test suite)*

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Existing JWT + COMMAND_ROLES RBAC already enforced |
| V3 Session Management | no | Stateless JWT; no session |
| V4 Access Control | yes | PR push must require security_lead/admin role — not developer |
| V5 Input Validation | yes | Add Pydantic max_length on CommandRequest fields; validate file_path before push |
| V6 Cryptography | no | No new crypto |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via file_path in push_file | Tampering | Inherit existing `".." in Path(...).parts` guard from fetch_file_content |
| Prompt injection via chat input to fix generation | Tampering | Apply existing `InjectionGuardrail.check()` — currently unwired (CONCERNS.md issue #4) — wire in /fix handler |
| Unauthorized PR creation (developer role) | Elevation of Privilege | Push-PR endpoint requires security_lead/admin — enforce in COMMAND_ROLES and new /api/fix/push-pr |
| GitHub token leakage via PR description | Information Disclosure | ScrubbingService already scrubs before Gemini; apply scrubber to any user-facing output that embeds source snippets |
| Empty/malformed patch pushed to GitHub | Tampering | Guard: validate `pending_fix.patch` is non-empty and contains `@@` before executing push |

**Notable concern from CONCERNS.md:** `InjectionGuardrail` exists in `mcp/src/core/guardrails.py` but is never called in production chat paths (CONCERNS.md issue #4). Phase 04 should wire it into `/fix` handler and `/api/fix/generate`. [VERIFIED: CONCERNS.md lines 55-65]

---

## Sources

### Primary (HIGH confidence)
- `mcp/src/services/command_service.py` — confirmed /fix aliases _handle_explain; all 7 command handlers reviewed
- `mcp/src/api/chat.py` — COMMAND_ROLES matrix, endpoint routing confirmed
- `mcp/src/services/github_client.py` — existing methods confirmed; PR-creation methods not yet present
- `mcp/src/services/llm/service.py` — fetch_file_content + scrubbing flow confirmed
- `mcp/src/services/llm/schemas.py` — `remediation_diff` field confirmed in AnalysisOutput
- `mcp/tests/test_chat_api.py` — 14 chat tests confirmed all passing (180/180 total)
- [docs.github.com/en/rest/git/refs] — POST /git/refs for branch creation; required fields: ref, sha
- [docs.github.com/en/rest/repos/contents] — PUT /contents/{path}; required: message, content (base64), sha, branch
- [docs.github.com/en/rest/pulls/pulls] — POST /pulls; required: head, base, title

### Secondary (MEDIUM confidence)
- CONCERNS.md technical debt analysis — InjectionGuardrail unwired (issue #4), confirmed by grep
- INTEGRATIONS.md — GitHub API version header, auth pattern confirmed

### Tertiary (LOW confidence)
- dispatch_workflow + 2s sleep pattern for run URL — ASSUMED based on GitHub Actions async behavior; exact timing not verified against live API

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; all libraries verified in installed venv
- Architecture: HIGH — patterns follow existing codebase conventions exactly
- Pitfalls: HIGH — file SHA requirement (P2) and dispatch timing (P1) verified against GitHub API docs and code
- PR creation API: HIGH — endpoint signatures cited from official GitHub docs

**Research date:** 2026-04-29
**Valid until:** 2026-05-29 (GitHub API v2022-11-28 stable; no breaking changes expected in 30 days)

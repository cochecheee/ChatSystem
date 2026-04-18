# Phase 5: Web Dashboard Development - Research

**Researched:** 2026-04-12
**Domain:** Frontend (React + Vite + TypeScript) / Security Visualization / ChatOps
**Confidence:** HIGH

## Summary

Phase 5 focuses on building a modern, responsive web dashboard to visualize security findings and interact with the CI/CD pipeline via a ChatOps interface. The technical stack leverages React 19 and Vite 8 for performance, with a heavy emphasis on developer experience and UI consistency using Shadcn/UI and Tailwind CSS 4.

**Primary recommendation:** Use **TanStack Query (v5)** for efficient 15s polling with dynamic intervals and **Shadcn/UI + cmdk** for the ChatOps command suggestion interface.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React | 19.2 | UI Framework | Current industry standard for component-based UIs. |
| Vite | 8.0 | Build Tool | Extremely fast HMR and optimized production builds. |
| TypeScript | 6.0 | Language | Type safety for complex security data structures. |
| Tailwind CSS | 4.2 | Styling | Utility-first CSS for rapid, maintainable UI development. [VERIFIED: npm registry] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Shadcn/UI | Latest | Component Library | Accessible, customizable UI primitives (Radix UI based). |
| Lucide React | 1.8.0 | Icons | Clean, consistent icon set for security actions. [VERIFIED: npm registry] |
| @tanstack/react-query | 5.99 | Data Fetching | Handles caching, polling, and synchronization. [VERIFIED: npm registry] |
| Recharts | 3.8 | Data Viz | Declarative charting library for React. [VERIFIED: npm registry] |
| React Markdown | 10.1 | Markdown | Rendering AI analysis and remediation suggestions. [VERIFIED: npm registry] |
| React Syntax Highlighter | 15.6 | Code Blocks | Syntax highlighting for suggested code fixes. |
| cmdk | 1.0.0 | Command Menu | Powering the slash-command suggestion list in ChatOps. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Recharts | Chart.js / D3.js | D3 is too low-level; Recharts is native to React and easier to maintain. |
| TanStack Query | SWR | SWR is lighter but TanStack Query has better devtools and more robust mutation state. |
| Polling | WebSockets | WebSockets provide lower latency but are harder to scale/debug; 15s polling meets the current requirements. |

## Architecture Patterns

### Recommended Project Structure
```
dashboard/src/
├── components/
│   ├── ui/             # Shadcn primitives
│   ├── security/       # SeverityBadge, FindingCard, FindingsTable
│   ├── charts/         # SeverityDistribution, ScannerStats
│   └── chat/           # ChatPanel, MessageBubble, CommandMenu
├── hooks/
│   ├── usePipeline.ts  # Polling and trigger logic
│   ├── useFindings.ts  # Data fetching for vulnerabilities
│   └── useChat.ts      # Command handling and state
├── services/
│   └── api.ts          # Axios/Fetch instances for MCP Gateway
└── lib/
    └── utils.ts        # Tailwind merge and formatting helpers
```

### Pattern 1: Dynamic Polling with React Query
**What:** Adjust polling frequency based on pipeline state.
**When to use:** To reduce API load when a pipeline is idle or completed.
**Example:**
```typescript
// Source: [CITED: tanstack.com/query/latest]
const { data: pipeline } = useQuery({
  queryKey: ['pipeline', 'latest'],
  queryFn: fetchLatestPipeline,
  // Poll every 5s if running, every 30s if idle, or 15s (default)
  refetchInterval: (query) => {
    const status = query.state.data?.status;
    if (status === 'RUNNING') return 5000;
    if (status === 'IDLE') return 30000;
    return 15000;
  },
});
```

### Pattern 2: ChatOps Slash Commands
**What:** Using `cmdk` to show a filtered list of commands when the user types `/`.
**When to use:** In the Chat Panel input to provide discoverable AI actions.
**Anti-Patterns to Avoid:**
- **Manual Input Parsing:** Don't use regex to parse every keystroke; use a specialized component like `cmdk` or a headless editor like TipTap for better UX. [CITED: tiptap.dev]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Charts | Custom SVG charts | Recharts | Accessibility, responsiveness, and pre-built components. |
| Markdown Rendering | `dangerouslySetInnerHTML` | React Markdown | Security (XSS prevention) and GFM support. |
| Code Highlighting | Manual string formatting | React Syntax Highlighter | Correct language parsing and theme support. |
| Modal/Popovers | Custom Z-index logic | Shadcn/Radix UI | Focus management and ARIA compliance. |

## Common Pitfalls

### Pitfall 1: Alert Fatigue (The "Rainbow Dashboard")
**What goes wrong:** Displaying too many high-contrast colors makes it hard to identify critical issues.
**How to avoid:** Use neutral tones for the background and reserve saturated colors (Red/Purple) only for **Critical** and **High** vulnerabilities. Use "Bento Grid" layouts to group related metrics. [CITED: designmonks.co]

### Pitfall 2: Markdown XSS
**What goes wrong:** AI-generated remediation code or snippets from scanners might contain malicious scripts.
**How to avoid:** Always use `rehype-sanitize` with `react-markdown` to strip dangerous HTML tags. [VERIFIED: React Security best practices]

### Pitfall 3: Polling Inefficiency
**What goes wrong:** Polling continues at 15s even when the user is on another tab, wasting battery and server resources.
**How to avoid:** TanStack Query pauses polling automatically when the tab is hidden. Ensure `refetchIntervalInBackground` remains `false` unless strictly necessary.

## Code Examples

### Severity Color Mapping (Tailwind 4)
```tsx
// Standardized severity visualization
const SEVERITY_CONFIG = {
  CRITICAL: "bg-red-900 text-white border-red-800",
  HIGH: "bg-red-500 text-white border-red-600",
  MEDIUM: "bg-orange-500 text-white border-orange-600",
  LOW: "bg-blue-500 text-white border-blue-600",
  INFO: "bg-slate-400 text-white border-slate-500",
} as const;

export const SeverityBadge = ({ level }: { level: keyof typeof SEVERITY_CONFIG }) => (
  <span className={`px-2 py-0.5 rounded-full text-xs font-bold border ${SEVERITY_CONFIG[level]}`}>
    {level}
  </span>
);
```

### Chat Command Suggester (Conceptual)
```tsx
import { Command, CommandGroup, CommandItem, CommandList } from "@/components/ui/command";

export const CommandMenu = ({ open, onSelect }: { open: boolean, onSelect: (cmd: string) => void }) => {
  if (!open) return null;
  return (
    <Command className="absolute bottom-full mb-2 w-full border rounded-lg shadow-xl bg-popover">
      <CommandList>
        <CommandGroup heading="Available Commands">
          <CommandItem onSelect={() => onSelect("/explain")}>/explain - Phân tích lỗ hổng</CommandItem>
          <CommandItem onSelect={() => onSelect("/fix")}>/fix - Đề xuất mã sửa lỗi</CommandItem>
          <CommandItem onSelect={() => onSelect("/status")}>/status - Kiểm tra pipeline</CommandItem>
          <CommandItem onSelect={() => onSelect("/rerun")}>/rerun - Chạy lại scan</CommandItem>
        </CommandGroup>
      </CommandList>
    </Command>
  );
};
```

## Integration with MCP

| Action | API Endpoint (MCP Gateway) | Method | Logic |
|--------|----------------------------|--------|-------|
| Get Findings | `/api/findings` | GET | List of normalized vulnerabilities. |
| Trigger Scan | `/api/pipeline/trigger` | POST | Starts a new GitHub Actions run. |
| AI Analysis | `/api/analysis/explain` | POST | Send `{ finding_id }` to trigger LLM analysis. |
| Command Execution | `/api/chat/execute` | POST | General endpoint for `/` commands. |

**Key pattern:** Use **Optimistic Updates** in React Query when a user triggers a scan or `/fix` action to show immediate feedback while the long-running process starts in the background.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Vitest + React Testing Library |
| Config file | `dashboard/vitest.config.ts` |
| Quick run command | `npm run test` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command |
|--------|----------|-----------|-------------------|
| DASH-01 | Render vulnerability list | Component | `vitest FindingsTable.test.tsx` |
| DASH-02 | Polling updates every 15s | Integration | `vitest usePipeline.test.ts` (using fake timers) |
| DASH-03 | Command suggest menu opens on `/` | UI/E2E | `vitest ChatInput.test.tsx` |
| DASH-04 | Charts display severity stats | Component | `vitest SeverityChart.test.tsx` |

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | Yes | Use `DOMPurify` for any external content rendering. |
| V12 File and Resources | Yes | Ensure artifact download links are signed/authenticated. |
| V14 Configuration | Yes | Environment variables (Vite prefixes `VITE_`) for API URLs. |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via Markdown | Tampering | Use `rehype-sanitize` with `react-markdown`. |
| Prompt Injection (UI) | Information Disclosure | UI-level validation of chat commands before sending to MCP. |

## Sources

### Primary (HIGH confidence)
- [Official React Query Docs] - Polling & Mutating patterns.
- [Shadcn/UI Docs] - Component usage and Command primitive.
- [NPM Registry] - Version verification for Tailwind, Recharts, Vite.

### Secondary (MEDIUM confidence)
- [Modern Security Dashboard Design Guides 2024] - Bento grid and color palette recommendations.
- [TipTap Suggestion Extension Docs] - Slash command implementation best practices.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Versions verified via npm registry.
- Architecture: HIGH - Industry standard patterns for AI/Dashboard apps.
- Pitfalls: MEDIUM - Based on common frontend issues in security tools.

**Research date:** 2026-04-12
**Valid until:** 2026-05-12 (Vite/Tailwind updates frequent)

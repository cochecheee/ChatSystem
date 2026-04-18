# Phase 5 Context: Web Dashboard Development

## Phase Goal
Build the React-based security dashboard with real-time polling and integrated ChatOps panel.

## Decisions

### UI/UX
- D-01: Use **Shadcn/UI** for core component library (Radix UI based).
- D-02: Implement a **Bento Grid** layout for high-level vulnerability insights.
- D-03: Use **Severity Badges** (Critical, High, Medium, Low, Info) with high contrast for critical/high.
- D-04: Securely render AI-generated Markdown with **rehype-sanitize** and **react-syntax-highlighter**.

### Data Fetching
- D-05: Use **TanStack Query (v5)** for all data fetching and state synchronization.
- D-06: Implement **Real-time Polling** with a 15-second interval (default), dynamic based on pipeline state (5s if running, 30s if idle).

### ChatOps
- D-07: Integrate a **Chat Panel** (ChatOps UI) with a scrolling message history.
- D-08: Support **Slash Commands** (/explain, /fix, /status, /scan, /results, /rerun, /approve, /report) with a suggestion menu (cmdk).

### Visualization
- D-09: Use **Recharts** for severity distribution and scanner statistics.

## Requirements Reference
- REQ-04-01: Real-time findings & pipeline status (15s polling).
- REQ-04-02: Chat Panel (ChatOps UI) with scrolling history.
- REQ-04-03: Slash command menu with automated actions.
- REQ-04-04: Severity summary charts.

## the agent's Discretion
- Choose appropriate Tailwind 4 color palette for the security domain.
- Implement responsive layout (Mobile-first).
- Use Axion or Fetch for API client depending on preference.

# Coding Conventions

**Analysis Date:** 2026-04-28

## Naming Patterns

**Files:**
- Python modules: `snake_case.py` — e.g., `normalizer.py`, `github_client.py`, `command_service.py`
- TypeScript components: `PascalCase.tsx` — e.g., `Vulns.tsx`, `Overview.tsx`, `Shell.tsx`
- TypeScript utilities/api: `camelCase.ts` — e.g., `client.ts`, `index.ts`
- Test files (Python): `test_<subject>.py` — e.g., `test_normalizer.py`, `test_chat_api.py`

**Functions:**
- Python: `snake_case` — e.g., `process_artifact`, `scrub_content`, `get_current_user`
- Python private helpers: leading underscore — e.g., `_run`, `_build_findings`, `_scrub_secrets`, `_is_security_artifact`
- TypeScript: `camelCase` — e.g., `authHeaders`, `setAuthToken`, `pkgMeta`
- React components: `PascalCase` — e.g., `SevChip`, `DiffView`, `CveUpdateCard`

**Variables:**
- Python: `snake_case` — e.g., `artifact_id`, `github_run_id`, `session_factory`
- TypeScript: `camelCase` — e.g., `openVulnId`, `vulnCount`, `critHighRef`
- TypeScript constants: `SCREAMING_SNAKE_CASE` — e.g., `_MAX_CONTENT_LENGTH` (Python), `SEVERITY_ORDER`, `DEP_SCAN_TOOLS`
- Module-level Python constants: prefixed with `_` for private — e.g., `_SARIF_LEVEL_TO_SEVERITY`, `_INJECTION_PATTERNS`

**Types/Classes:**
- Python classes: `PascalCase` — e.g., `SecurityProcessor`, `ScrubbingService`, `InjectionGuardrail`, `BaseNormalizer`
- Python enums: `PascalCase` with lowercase values — e.g., `ArtifactStatus.pending`
- TypeScript interfaces: `PascalCase` prefixed with `I` is NOT used — plain `PascalCase` — e.g., `Finding`, `WorkflowRun`, `CommandRequest`
- TypeScript type aliases: `PascalCase` — e.g., `Severity`, `PageId`
- Pydantic models: `PascalCase` with `Create`/`Out`/`Request`/`Response` suffixes — e.g., `FindingCreate`, `FindingOut`, `ProcessRequest`, `CommandResponse`

**Directories:**
- Python packages: `snake_case` — e.g., `src/api/`, `src/core/`, `src/models/`, `src/services/`
- TypeScript directories: `lowercase` — e.g., `src/api/`, `src/components/`, `src/pages/`, `src/types/`

## Code Style

**Formatting (TypeScript/Dashboard):**
- No Prettier config detected — formatting enforced through ESLint
- ESLint config: `dashboard/eslint.config.js` (flat config format, ESLint v9)
- Rules: `@eslint/js` recommended + `typescript-eslint` recommended + `eslint-plugin-react-hooks` + `eslint-plugin-react-refresh`
- Target: `ecmaVersion: 2020`, browser globals
- Files: `**/*.{ts,tsx}` — `dist/` is globally ignored

**Formatting (Python/MCP):**
- No `pyproject.toml`, `.pylintrc`, or formatter config detected
- Code style observed: PEP-8 compliant, 4-space indentation, 79-100 char line lengths
- Type hints used throughout (`from __future__ import annotations` at top of most files)

**Linting commands:**
```bash
# Dashboard
cd dashboard && npm run lint          # ESLint over all TS/TSX

# Python — no configured linter script detected; run manually:
cd mcp && python -m pylint src/       # if pylint installed
```

## Import Organization

**Python:**
1. `from __future__ import annotations` (first, if used)
2. Standard library imports (`import asyncio`, `import logging`, `import os`)
3. Third-party imports (`from fastapi import ...`, `from sqlalchemy import ...`)
4. Local relative imports (`from ..core.config import settings`, `from ..models.entities import ...`)
- Relative imports are always used within the `mcp/src/` package

**TypeScript:**
1. React/framework imports (`import { useEffect, useState } from 'react'`)
2. Third-party library imports
3. Local imports from `../api/`, `../components/`, `../types/`, `../utils/`
- All imports use named exports; no default export for components except `App.tsx`

## Module Organization

**Python (`mcp/src/`):**
```
src/
  main.py          — FastAPI app factory, lifespan, router registration
  api/             — HTTP route handlers (thin: validate, dispatch, return)
    artifacts.py   — /projects, /artifacts, /findings, /github/*, /webhook/*
    analysis.py    — /findings/{id}/explain
    chat.py        — /api/chat/* (auth, commands, report)
  core/            — Cross-cutting infrastructure
    config.py      — pydantic-settings Settings singleton
    db.py          — SQLAlchemy engine, Base, get_session, init_db
    auth.py        — JWT encode/decode, get_current_user dependency
    guardrails.py  — ScrubbingService, InjectionGuardrail
  models/          — Data layer
    entities.py    — SQLAlchemy ORM (Project, Artifact, Finding)
    schemas.py     — Pydantic request/response schemas
  services/        — Business logic
    processor.py   — SecurityProcessor (orchestrates full pipeline)
    normalizer.py  — NormalizerFactory + per-format normalizers
    enricher.py    — DataEnricher (CWE→CVSS scoring)
    github_client.py — GitHub API calls
    poller.py      — GitHubPoller background task
    command_service.py — ChatOps command handler
    report_service.py  — HTML report generation
    llm/           — LLM integration sub-package
```

**TypeScript (`dashboard/src/`):**
```
src/
  main.tsx         — React root mount
  App.tsx          — Root component, routing via state, polling loop
  api/
    client.ts      — Fetch wrapper (get/post helpers), token management
    index.ts       — Re-exports (barrel)
  components/
    Shell.tsx      — Sidebar, Topbar, PageId type
    Charts.tsx     — Chart components
    Icon.tsx       — SVG icon abstraction
    modals/        — Modal components
  pages/           — One file per route: Overview, Pipelines, Vulns, Chat, Reports, Settings
  types/
    index.ts       — All TypeScript interfaces and types (single source of truth)
  utils/           — Shared helpers (toast notifications, etc.)
```

## Error Handling Patterns

**Python (FastAPI):**
- Raise `HTTPException` with explicit status codes at the API layer: `raise HTTPException(status_code=404, detail="...")`
- Services do NOT raise `HTTPException` — they raise Python exceptions (`ValueError`, generic `Exception`)
- The API layer catches service exceptions and converts to appropriate HTTP status codes
- Background tasks catch and log exceptions via `log.error(...)`, then mark artifact as `"failed"` status
- Pattern in `processor.py`: `try/except Exception` wraps the full pipeline; sets `artifact.status = "failed"` then re-raises

**TypeScript:**
- `fetch` wrappers in `api/client.ts` throw `Error` on non-ok responses: `throw new Error(...)`
- Components consume these via `.catch(() => {})` (silent failure for polling) or propagated to UI
- No global error boundary detected

## Logging Patterns

**Python:**
- Framework: `logging` (stdlib) — `logging.getLogger(__name__)` at module level
- Log variable: `log` (not `logger`) — consistent across all service modules
- Levels used:
  - `log.info(...)` — normal pipeline events (artifact counts, poller scheduling)
  - `log.warning(...)` — recoverable errors (failed file normalization, skipped files)
  - `log.error(...)` — hard failures (artifact processing failure with exception)
- Structured format using `%s` printf-style in log calls (not f-strings)
- Example: `log.info("Stored %d findings for artifact %d", len(db_findings), db_artifact_id)`
- No structured logging framework (e.g., structlog) — plain stdlib logging

**TypeScript:**
- No logging framework; debug-only `console.*` used sporadically
- User feedback via `sonner` toast notifications (`src/utils/toast.py`)

## Common Patterns

**Dependency Injection (FastAPI):**
- `Depends(get_session)` — async DB session per request
- `Depends(get_current_user)` — JWT authentication
- `Depends(get_github_client)` — GitHub API client
- Test overrides via `app.dependency_overrides[get_xxx] = lambda: mock_xxx`

**Pydantic for Validation:**
- All API inputs are Pydantic models; extra fields are `model_config = {"extra": "ignore"}`
- ORM read models use `model_config = {"from_attributes": True}`
- Settings via `pydantic-settings`: `BaseSettings` with `.env` file support

**Abstract Base Classes:**
- `BaseNormalizer` (ABC) in `mcp/src/services/normalizer.py` — `normalize()` is `@abstractmethod`
- Factory pattern: `NormalizerFactory.get(filename, content)` returns correct `BaseNormalizer` subclass

**Service Layer Composition:**
- `SecurityProcessor` accepts injected dependencies in `__init__` for testability:
  ```python
  def __init__(self, session_factory=None, github_client=None, scrubber=None, enricher=None):
  ```
- Defaults to real implementations; tests pass `AsyncMock` objects

**Type Annotations:**
- Python: full type annotations using `|` union syntax (Python 3.10+ style), enabled by `from __future__ import annotations`
- `Mapped[T]` for SQLAlchemy columns: `id: Mapped[int] = mapped_column(...)`
- TypeScript: explicit interface types imported from `src/types/index.ts`

**Constants as Module-Level Frozen Sets:**
- `_SECURITY_ARTIFACT_NAMES = frozenset({...})` — immutable set of known artifact name strings
- Predicate functions wrap the constants: `def _is_security_artifact(name: str) -> bool`

---

*Convention analysis: 2026-04-28*

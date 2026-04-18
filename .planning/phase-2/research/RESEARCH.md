# Phase 2: MCP Gateway Server Development - Research

**Researched:** 2026-04-12 (Updated: 2026-04-16)
**Domain:** Security Middleware / MCP / SAST Data Processing
**Confidence:** HIGH

## Summary

Phase 2 focuses on building the **MCP Gateway Server**, which acts as a secure middleware between CI/CD pipelines (GitHub Actions) and the AI Analysis layer (Gemini). This server is responsible for fetching SAST results, normalizing them into a unified schema, enriching findings with industry standards (CWE/OWASP/CVSS), and enforcing security guardrails (PII/Secret scrubbing and Prompt Injection protection).

**Primary recommendation:** Use `sarif-pydantic` for core data modeling and implement a modular "Normalization Layer" that converts XML/JSON outputs from diverse tools (Semgrep, Bandit, Dependency-Check) into a unified SARIF-compatible Pydantic schema before storage in SQLite via SQLAlchemy.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `fastapi` | ^0.110.0 | API Framework | High performance, async-first, excellent Pydantic integration. |
| `sarif-pydantic` | >=0.6.2 | SARIF Data Model | Native Pydantic v2 models for the SARIF 2.1.0 spec. [VERIFIED: pypi — latest is 0.6.2, not 2.x] |
| `sqlalchemy` | ^2.0.0 | ORM | Industry standard for Python database interactions; supports async. |
| `aiosqlite` | ^0.20.0 | Async SQLite Driver | Required for async SQLAlchemy with SQLite. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `cwe2` | ^2.0.0 | CWE/OWASP Mapping | Mapping findings to CWE IDs and OWASP Top 10 categories. [CITED: cwe2 docs] |
| `cvss` | ^3.0.0 | CVSS Scoring | Calculating/parsing CVSS 3.1 vectors from SAST tools. |
| `detect-secrets` | ^1.5.0 | Secret Detection | Scanning artifacts for leaked credentials before AI analysis. [VERIFIED: github.com/Yelp/detect-secrets] |
| `requests` | ^2.31.0 | GitHub API Client | Simple synchronous fetching of artifacts (standard for CLI/Jobs). |
| `httpx` | ^0.27.0 | Async HTTP Client | Recommended for async calls within FastAPI endpoints. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `sarif-pydantic` | `sarif-om` | Official MS library but uses legacy classes, not Pydantic-friendly. |
| `cwe2` | MITRE CSVs | Manual parsing of MITRE data; `cwe2` is more convenient but potentially less fresh. |
| `detect-secrets` | `Gitleaks` | Gitleaks is faster (Go) but harder to integrate as a pure Python library. |

**Installation:**
```bash
pip install fastapi uvicorn sqlalchemy aiosqlite pydantic sarif-pydantic cwe2 cvss detect-secrets defusedxml httpx python-dotenv python-jose passlib slowapi
```

## Architecture Patterns

### Recommended Project Structure
```
mcp/
├── src/
│   ├── api/             # FastAPI routes (Artifacts, Analysis, Health)
│   ├── core/            # Config, Security Guardrails, Loggers
│   ├── models/          # Pydantic Schemas & SQLAlchemy Entities
│   ├── services/        # Business Logic (GitHub Client, Normalizer, Enricher)
│   └── main.py          # App entry point
├── tests/               # Pytest suite
└── requirements.txt
```

### Pattern 1: Modular Normalization (Adapter Pattern)
**What:** Each SAST tool (Semgrep, SpotBugs, etc.) has its own "Adapter" class that converts its native output (JSON/XML) into the unified `sarif-pydantic` model.
**When to use:** When handling diverse output formats (SARIF, JUnit XML, Bandit JSON).
**Example:**
```python
# Source: Internal design pattern for SAST Aggregators
class BaseNormalizer:
    async def normalize(self, content: str) -> SarifLog:
        pass

class BanditNormalizer(BaseNormalizer):
    async def normalize(self, content: str) -> SarifLog:
        # Map Bandit JSON fields to SARIF fields
        pass
```

### Anti-Patterns to Avoid
- **Hand-rolling Secret Detection:** Do not use custom regex for high-entropy secrets; use `detect-secrets` plugins. [ASSUMED]
- **Blocking Async Loops:** Avoid using `requests` inside FastAPI `async def` routes; use `httpx` or run `requests` in a threadpool.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SARIF Validation | Custom Regex/Validation | `sarif-pydantic` | SARIF spec is 100+ pages; manual validation is error-prone. |
| CWE/OWASP Mapping | Static Dictionaries | `cwe2` | Mappings change; `cwe2` abstracts the MITRE database. |
| Entropy Calculation | Custom Shannon Math | `detect-secrets` | Already handles edge cases for Base64/Hex encoding. |

## Common Pitfalls

### Pitfall 1: GitHub Artifact Expiration
**What goes wrong:** Artifacts are deleted after 90 days (default) or even shorter.
**Why it happens:** GitHub storage costs; retention policies.
**How to avoid:** Download and store results in the local SQLite database immediately after the CI run completes.

### Pitfall 2: Async SQLite Write Locks
**What goes wrong:** "Database is locked" errors during concurrent writes.
**Why it happens:** SQLite only supports one concurrent writer.
**How to avoid:** Use a single database connection for writes or configure `aiosqlite` with appropriate timeouts and `PRAGMA journal_mode=WAL;`. [CITED: SQLAlchemy docs]

## Code Examples

### GitHub Artifact Download (Python/Requests)
```python
# Source: GitHub REST API Docs (modified for Python)
import requests
import zipfile
import io

def download_artifact(owner, repo, artifact_id, token):
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        # Extract and find .sarif or .xml files
        return {name: z.read(name).decode('utf-8') for name in z.namelist()}
```

### Async SQLAlchemy Session Management
```python
# Source: SQLAlchemy 2.0 Asyncio docs
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine("sqlite+aiosqlite:///./mcp.db")
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Custom XML Parsers | `sarif-pydantic` | 2023+ | Type-safety for security findings. |
| Sync `sqlite3` | `aiosqlite` + SQLAlchemy 2.0 | 2022 | Non-blocking database ops in FastAPI. |
| Manual Regex Guardrails | LLM Guard / Rebuff | 2024 | Better protection against indirect injection. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `detect-secrets` is sufficient for initial PII/Secret scrubbing. | Core Stack | Might miss project-specific PII formats. |
| A2 | SQLite with WAL mode handles Phase 2 concurrency. | Common Pitfalls | Might need Postgres if dashboard polling is too high. |
| A3 | OWASP Top 10 2021 mapping is sufficient for AI analysis. | Supporting | User might expect OWASP 2024 (not yet standard). |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | ✓ | 3.13.1 | — |
| Pip | Installation | ✓ | 25.3 | — |
| SQLite3 | Database | ✗ | — | Python `sqlite3` / `aiosqlite` |
| GitHub Token | Artifact Fetching | ✗ | — | Required env var (PAT) |

**Missing dependencies with no fallback:**
- **GitHub Token (PAT):** Must be provided via `.env` or CI secrets.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` |
| Config file | `pytest.ini` |
| Quick run command | `pytest -m "not slow"` |
| Full suite command | `pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REQ-2.1 | Fetch Artifacts from GitHub | Integration | `pytest tests/test_github_client.py` | ❌ Wave 0 |
| REQ-2.2 | Normalize XML to SARIF | Unit | `pytest tests/test_normalizers.py` | ❌ Wave 0 |
| REQ-2.3 | Scrub PII/Secrets | Unit | `pytest tests/test_guardrails.py` | ❌ Wave 0 |
| REQ-2.4 | Enrich Findings (CWE/CVSS) | Unit | `pytest tests/test_enricher.py` | ❌ Wave 0 |

### Wave 0 Gaps
- [ ] `tests/conftest.py` — Shared fixtures for mocked GitHub responses.
- [ ] `mcp/pytest.ini` — Test configuration.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | Yes | Pydantic schema validation for all SAST inputs. |
| V6 Cryptography | Yes | Encryption of sensitive findings in transit (HTTPS). |
| V13 API & Web Service | Yes | Secure handling of GitHub PATs (SOPS/Env). |

### Known Threat Patterns for Python Middleware

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt Injection | Tampering | Use delimiters (e.g., `###`) and Rebuff/Lakera Guard. |
| Zip Slip (Artifacts) | Tampering | Sanitize extraction paths for artifacts. [CITED: Snyk] |
| Secret Leakage (Logs) | Info Disclosure | Implement custom logging filter to mask secrets. |

## Sources

### Primary (HIGH confidence)
- GitHub REST API Docs - Artifacts & Code Scanning endpoints.
- `sarif-pydantic` GitHub Repository - Model definitions.
- SQLAlchemy 2.0 Official Documentation - Asyncio patterns.

### Secondary (MEDIUM confidence)
- `detect-secrets` README - Plugin capabilities.
- `cwe2` PyPI - Mapping features.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Libraries are modern and verified.
- Architecture: HIGH - Adapter pattern is standard for multi-format processing.
- Pitfalls: MEDIUM - SQLite performance depends on real-world load.

**Research date:** 2026-04-12
**Valid until:** 2026-05-12

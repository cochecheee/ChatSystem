"""Anthropic Model Context Protocol server — V2.7 / báo cáo tiến độ ch.3.2.

Exposes the chat-system data + actions as MCP tools so AI clients
(Claude Desktop, Cursor, Continue) can connect via stdio/HTTP and
query findings or kick off scans through natural-language calls.

Re-uses the same SQLAlchemy engine + repositories the FastAPI app
uses — both processes share `mcp.db` (SQLite) or the Render Postgres.
Running this server alongside `uvicorn src.main:app` is the documented
"dual-protocol" deployment in `docs/mcp-server.md`.

Run:
    # stdio — what Claude Desktop launches as a subprocess
    python -m src.mcp_server

    # HTTP+SSE — for browser-based MCP inspectors
    python -m src.mcp_server --transport http --port 8765
"""
from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime

from fastmcp import FastMCP

from .core.auth import User
from .core.config import settings
from .core.db import AsyncSessionLocal
from .models.entities import Finding
from .models.schemas import CommandRequest
from .repositories import FindingRepository
from .services.command_service import CommandService
from .services.github_client import GitHubClient
from .services.llm.service import LLMAnalysisService
from .services.stats_service import StatsService

log = logging.getLogger(__name__)

mcp = FastMCP(
    name="sast-chat-mcp",
    instructions=(
        "MCP server cho hệ thống SAST/SCA dashboard chat-system. "
        "Cung cấp tools đọc findings, phân tích AI tiếng Việt, "
        "phê duyệt/thu hồi, kích hoạt scan workflow. "
        "Mọi action mutate (approve/revoke/scan) đều ghi audit trail "
        "vào submitted_by=mcp:<role> để phân biệt với UI/CI caller."
    ),
)


# ---------------------------------------------------------------------------
# Helpers — re-use existing services with a synthetic User
# ---------------------------------------------------------------------------

def _user(role: str = "security_lead") -> User:
    """MCP caller acts as security_lead by default — they can read findings
    and run /approve and /revoke. Override per-tool when stricter scope is
    required. Username `mcp:<role>` tags the audit trail so we can later
    distinguish AI agent actions from human dashboard clicks."""
    return User(username=f"mcp:{role}", role=role)


def _serialize_finding(f: Finding) -> dict:
    return {
        "id": f.id,
        "artifact_id": f.artifact_id,
        "tool": f.tool,
        "rule_id": f.rule_id,
        "severity": f.severity,
        "message": f.message,
        "file_path": f.file_path,
        "line_number": f.line_number,
        "cwe_id": f.cwe_id,
        "cvss_score": f.cvss_score,
        "status": f.status,
        "ai_analysis": f.ai_analysis,
        "approved_by": f.approved_by,
        "approved_at": f.approved_at.isoformat() if f.approved_at else None,
        "revoked_by": f.revoked_by,
        "revoked_at": f.revoked_at.isoformat() if f.revoked_at else None,
        "normalized_at": f.normalized_at.isoformat() if f.normalized_at else None,
    }


# ---------------------------------------------------------------------------
# Tools — 8 minimal surface per .planning/redesign/PHASE-V2.7
# ---------------------------------------------------------------------------

@mcp.tool
async def list_findings(
    severity: str | None = None,
    category: str | None = None,
    status: str | None = None,
    tool: str | None = None,
    query: str | None = None,
    limit: int = 50,
) -> dict:
    """List findings matching the filter.

    Args:
        severity: critical | high | medium | low | info
        category: sast | deps | dast
        status:   pending_review | ai_analyzed | APPROVED | REVOKED
        tool:     semgrep | codeql | trivy | bandit | safety | spotbugs | dependency-check | owasp-zap | ...
        query:    case-insensitive substring filter against message / file_path / rule_id
        limit:    max rows (cap 200)
    """
    limit = max(1, min(200, int(limit)))
    async with AsyncSessionLocal() as session:
        repo = FindingRepository(session)
        rows = await repo.list_with_filters(
            severity=severity,
            tool=tool,
            status=status,
            category=category,
            q=query,
            skip=0,
            limit=limit,
        )
        total = await repo.count_with_filters(
            severity=severity, tool=tool, status=status, category=category, q=query,
        )
        return {
            "total_matching": total,
            "returned": len(rows),
            "items": [_serialize_finding(f) for f in rows],
        }


@mcp.tool
async def get_finding(finding_id: int) -> dict:
    """Return a single finding by id, including AI analysis if it has run."""
    async with AsyncSessionLocal() as session:
        f = await FindingRepository(session).get(int(finding_id))
        if f is None:
            return {"error": "not_found", "finding_id": finding_id}
        return _serialize_finding(f)


@mcp.tool
async def explain_finding(finding_id: int) -> dict:
    """Run the Gemini analyzer on a finding and return remediation diff
    (tiếng Việt). Cached after first call — re-running returns the cache."""
    async with AsyncSessionLocal() as session:
        f = await FindingRepository(session).get(int(finding_id))
        if f is None:
            return {"error": "not_found", "finding_id": finding_id}
        if f.status == "ai_analyzed" and f.ai_analysis:
            return {"cached": True, **f.ai_analysis}
        try:
            result = await LLMAnalysisService().analyze_finding(f, session)
        except RuntimeError as exc:
            return {"error": "ai_unavailable", "detail": str(exc)}
        except ValueError as exc:
            return {"error": "rejected_by_guardrail", "detail": str(exc)}
        return {"cached": False, **result.model_dump()}


@mcp.tool
async def approve_finding(finding_id: int, justification: str) -> dict:
    """Mark a finding APPROVED (false-positive accepted). Justification
    must be ≥ 20 chars — same rule as the ChatOps /approve command. Audit
    trail records submitted_by=mcp:security_lead."""
    async with AsyncSessionLocal() as session:
        cs = CommandService()
        try:
            resp = await cs.handle(
                "approve",
                CommandRequest(
                    command="/approve",
                    finding_id=int(finding_id),
                    justification=justification,
                ),
                _user("security_lead"),
                session,
            )
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}
        return resp.model_dump()


@mcp.tool
async def revoke_finding(finding_id: int, justification: str) -> dict:
    """Revoke a previously approved finding (e.g. new evidence of exploit).
    Justification ≥ 20 chars. Audit trail records mcp:security_lead."""
    async with AsyncSessionLocal() as session:
        cs = CommandService()
        try:
            resp = await cs.handle(
                "revoke",
                CommandRequest(
                    command="/revoke",
                    finding_id=int(finding_id),
                    justification=justification,
                ),
                _user("security_lead"),
                session,
            )
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}
        return resp.model_dump()


@mcp.tool
async def list_pipelines(limit: int = 20) -> dict:
    """Most recent GitHub Actions workflow runs for the configured repo."""
    limit = max(1, min(50, int(limit)))
    try:
        runs = await GitHubClient().list_workflow_runs(workflow_name="", branch="", status="")
    except Exception as exc:
        return {"error": "github_unreachable", "detail": str(exc)}
    out = []
    for r in runs[:limit]:
        out.append({
            "id": r.get("id"),
            "run_number": r.get("run_number"),
            "name": r.get("name"),
            "status": r.get("status"),
            "conclusion": r.get("conclusion"),
            "head_branch": r.get("head_branch"),
            "head_sha": r.get("head_sha"),
            "created_at": r.get("created_at"),
            "html_url": r.get("html_url"),
        })
    return {"repo": f"{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}", "items": out}


@mcp.tool
async def get_stats_overview() -> dict:
    """Aggregated KPI: total / critical+high / AI-analyzed / per severity /
    per tool / per category — same shape the dashboard `/stats/overview`
    endpoint returns."""
    async with AsyncSessionLocal() as session:
        return await StatsService(session).overview()


@mcp.tool
async def trigger_scan(workflow_filename: str = "security.yml") -> dict:
    """Dispatch a GitHub workflow_dispatch event for the configured repo.
    Default workflow file `security.yml`. Returns success or upstream error."""
    try:
        await GitHubClient().dispatch_workflow(workflow_filename, ref="main")
        return {
            "status": "ok",
            "dispatched_by": "mcp:security_lead",
            "workflow": workflow_filename,
            "repo": f"{settings.GITHUB_OWNER}/{settings.GITHUB_REPO}",
            "dispatched_at": datetime.now(UTC).isoformat(),
        }
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="chat-system MCP server")
    parser.add_argument(
        "--transport", choices=["stdio", "http"], default="stdio",
        help="stdio (Claude Desktop default) or http+SSE for MCP Inspector",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()

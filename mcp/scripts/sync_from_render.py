"""Sync data from the Render-deployed MCP back to the local SQLite DB.

Why: local and Render are two completely separate databases. Even on the
same code branch, the two ingest different GitHub workflow runs at
different times, so dashboards diverge. This script makes local a
read-only mirror of Render at a point in time so you can demo offline,
debug with real data, or screenshot a consistent state.

What it does:
  1. POST /api/chat/auth/token to Render (as admin) — gets a JWT.
  2. GET  /projects                              → list of projects.
  3. GET  /projects/{id}/members                 → memberships.
  4. GET  /projects/{id}/suppressions            → suppression rules (best-effort).
  5. GET  /findings (paginated)                  → all findings caller can see.
  6. WIPE local findings + artifacts + suppression_rules + project_members
     + projects (FK order), then INSERT fresh rows.
  7. Re-encrypt secrets (github_token, gemini_api_key) with LOCAL FERNET_KEY
     since ProjectOut doesn't expose them — we pull from local .env.

Limitations:
  - github_artifact_id is regenerated as "sync-<artifact_id>" since the
    original CI artifact IDs aren't exposed via the API.
  - github_run_id falls back to Project.last_processed_run_id (artifact
    granularity below run-level is lost). The Pipelines page picker will
    therefore show fewer distinct runs than Render until a fresh poll
    runs against the same repo.
  - AlertItems and UptimeChecks are NOT synced (operational data is
    instance-specific and would mislead if shown alongside real findings).

Usage:
    python -m scripts.sync_from_render            # dry-run, prints counts
    python -m scripts.sync_from_render --apply    # actually wipe + insert
    python -m scripts.sync_from_render --apply --url https://other-mcp.example.com
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import datetime, UTC
from typing import Any

import httpx
from sqlalchemy import delete, select, text

from src.core.config import settings
from src.core.db import AsyncSessionLocal, init_db
from src.models.entities import (
    Alert,
    Artifact,
    Finding,
    Project,
    ProjectMember,
    SuppressionRule,
    UptimeCheck,
)
from src.repositories.project_repo import _encrypt_kwargs

log = logging.getLogger("sync_from_render")

DEFAULT_URL = "https://mcp-l958.onrender.com"
ADMIN_USERNAME = "sync-script"
PAGE_SIZE = 200          # /findings cap
TIMEOUT = httpx.Timeout(60.0, connect=30.0)  # cold start on Render free


# ---------------------------------------------------------------------------
# Render fetchers
# ---------------------------------------------------------------------------

async def login(client: httpx.AsyncClient) -> str:
    r = await client.post(
        "/api/chat/auth/token",
        json={"username": ADMIN_USERNAME, "role": "admin"},
    )
    r.raise_for_status()
    return r.json()["access_token"]


async def fetch_projects(client: httpx.AsyncClient, headers: dict) -> list[dict]:
    r = await client.get("/projects", headers=headers)
    r.raise_for_status()
    return r.json()


async def fetch_members(
    client: httpx.AsyncClient, headers: dict, project_id: int,
) -> list[dict]:
    r = await client.get(f"/projects/{project_id}/members", headers=headers)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return r.json()


async def fetch_suppressions(
    client: httpx.AsyncClient, headers: dict, project_id: int,
) -> list[dict]:
    r = await client.get(
        f"/projects/{project_id}/suppressions?include_expired=true",
        headers=headers,
    )
    if r.status_code != 200:
        return []
    return r.json()


async def fetch_all_findings(
    client: httpx.AsyncClient, headers: dict, project_id: int | None = None,
) -> list[dict]:
    """Page through /findings until we've pulled everything."""
    out: list[dict] = []
    skip = 0
    total: int | None = None
    while True:
        params: dict[str, Any] = {"skip": skip, "limit": PAGE_SIZE}
        if project_id is not None:
            params["project_id"] = project_id
        r = await client.get("/findings", headers=headers, params=params)
        r.raise_for_status()
        batch = r.json()
        if total is None:
            total = int(r.headers.get("X-Total-Count", len(batch)))
        out.extend(batch)
        log.info(
            "  fetched %d/%d (project_id=%s)", len(out), total, project_id,
        )
        if len(batch) < PAGE_SIZE or len(out) >= total:
            break
        skip += PAGE_SIZE
    return out


# ---------------------------------------------------------------------------
# Local DB writers
# ---------------------------------------------------------------------------

_TABLES_TO_WIPE_IN_FK_ORDER = (
    Finding, Artifact, SuppressionRule, ProjectMember,
    Alert, UptimeCheck, Project,
)


async def wipe_local() -> None:
    """Delete all rows in tables we sync — FK order matters."""
    async with AsyncSessionLocal() as session:
        for model in _TABLES_TO_WIPE_IN_FK_ORDER:
            await session.execute(delete(model))
        # Reset autoincrement so re-inserts can use original IDs (matters
        # for findings.artifact_id FK consistency). The sqlite_sequence
        # table is created lazily by SQLite on first AUTOINCREMENT insert,
        # so it may not exist on a freshly-init'd DB — ignore that case.
        if "sqlite" in settings.DATABASE_URL:
            try:
                await session.execute(text(
                    "DELETE FROM sqlite_sequence WHERE name IN "
                    "('findings','artifacts','projects','project_members',"
                    "'suppression_rules','alerts','uptime_checks')"
                ))
            except Exception:
                pass
        await session.commit()


def _project_to_orm(p: dict, fallback_credentials: dict) -> Project:
    """Map Render's ProjectOut JSON → local Project ORM row.

    `github_token` and `gemini_api_key` aren't exposed by ProjectOut for
    security — we pull them from local env so the local clone is usable
    for polling/AI calls. The `_encrypt_kwargs` step re-encrypts under
    the LOCAL FERNET_KEY (different from Render's; that's fine because
    we never re-decrypt Render-encrypted data here).
    """
    fields = dict(
        name=p["name"],
        github_url=p["github_url"],
        github_owner=p.get("github_owner", ""),
        github_repo=p.get("github_repo", ""),
        gemini_model=p.get("gemini_model", "") or "gemini-2.5-flash",
        artifact_profile=p.get("artifact_profile", "github-actions-default"),
        polling_workflow_name=p.get("polling_workflow_name", "Security"),
        polling_branch=p.get("polling_branch", "main"),
        active=1 if p.get("active", True) else 0,
        last_processed_run_id=p.get("last_processed_run_id"),
        # Credentials from local env — Render's API hides them, so without
        # this the project rows would be unable to poll or call Gemini.
        github_token=fallback_credentials.get("github_token", ""),
        gemini_api_key=fallback_credentials.get("gemini_api_key", ""),
    )
    encrypted = _encrypt_kwargs(fields)
    proj = Project(**encrypted)
    # Preserve original id so finding/artifact FKs sync cleanly.
    proj.id = p["id"]
    return proj


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def sync(url: str, apply: bool) -> None:
    fallback_credentials = {
        "github_token": settings.GITHUB_TOKEN or "",
        "gemini_api_key": settings.GEMINI_API_KEY or "",
    }
    if not fallback_credentials["gemini_api_key"]:
        log.warning(
            "GEMINI_API_KEY is unset locally — synced projects will lack AI "
            "credentials; /explain will fall back to legacy if at all.",
        )

    print(f"=== Connecting to {url} ===")
    async with httpx.AsyncClient(base_url=url, timeout=TIMEOUT) as client:
        # Trigger cold start, then auth.
        try:
            await client.get("/health")
        except Exception as exc:
            log.warning("Health check failed (continuing): %s", exc)
        token = await login(client)
        headers = {"Authorization": f"Bearer {token}"}
        print("  authenticated as admin")

        projects = await fetch_projects(client, headers)
        print(f"  {len(projects)} project(s) discovered:")
        for p in projects:
            print(f"    id={p['id']} {p['name']!r} → {p['github_url']}")

        # Per-project metadata
        members_by_project: dict[int, list[dict]] = {}
        suppressions_by_project: dict[int, list[dict]] = {}
        for p in projects:
            members_by_project[p["id"]] = await fetch_members(
                client, headers, p["id"],
            )
            suppressions_by_project[p["id"]] = await fetch_suppressions(
                client, headers, p["id"],
            )
        m_total = sum(len(v) for v in members_by_project.values())
        s_total = sum(len(v) for v in suppressions_by_project.values())
        print(f"  {m_total} membership row(s), {s_total} suppression rule(s)")

        # Findings — paginate per project so X-Total-Count is per-scope.
        all_findings: list[dict] = []
        for p in projects:
            all_findings.extend(
                await fetch_all_findings(client, headers, project_id=p["id"]),
            )
        print(f"  {len(all_findings)} finding(s) total")

    # ---------------------------------------------------------------------
    # Dry-run summary
    # ---------------------------------------------------------------------
    if not apply:
        print("\n(Dry-run — pass --apply to wipe + re-insert local DB)")
        return

    # ---------------------------------------------------------------------
    # Apply: wipe + insert
    # ---------------------------------------------------------------------
    print("\n=== Applying to local DB ===")
    await init_db()  # ensure schema (incl. webhook_token col)
    await wipe_local()
    print("  local tables wiped")

    async with AsyncSessionLocal() as session:
        # 1) projects (preserve ids)
        for p in projects:
            session.add(_project_to_orm(p, fallback_credentials))
        await session.commit()
        print(f"  inserted {len(projects)} project row(s)")

        # 2) memberships
        member_rows = 0
        for pid, members in members_by_project.items():
            for m in members:
                session.add(ProjectMember(
                    project_id=pid,
                    username=m["username"],
                    role=m["role"],
                    created_at=datetime.fromisoformat(m["created_at"])
                    if m.get("created_at") else datetime.now(UTC),
                ))
                member_rows += 1
        await session.commit()
        print(f"  inserted {member_rows} membership row(s)")

        # 3) suppressions
        sup_rows = 0
        for pid, sups in suppressions_by_project.items():
            for s in sups:
                session.add(SuppressionRule(
                    project_id=pid,
                    rule_id=s.get("rule_id"),
                    file_glob=s.get("file_glob"),
                    tool=s.get("tool"),
                    severity_max=s.get("severity_max"),
                    reason=s.get("reason", ""),
                    created_by=s.get("created_by", "sync"),
                    created_at=datetime.fromisoformat(s["created_at"])
                    if s.get("created_at") else datetime.now(UTC),
                    expires_at=datetime.fromisoformat(s["expires_at"])
                    if s.get("expires_at") else None,
                ))
                sup_rows += 1
        await session.commit()
        print(f"  inserted {sup_rows} suppression rule(s)")

        # 4) artifacts — synthesize one row per (project_id, artifact_id)
        #    we see in findings. Preserves the FK so finding rows still
        #    join. github_artifact_id is a placeholder "sync-{id}".
        artifact_keys = {
            (f["project_id"], f["artifact_id"])
            for f in all_findings
            if f.get("project_id") is not None and f.get("artifact_id") is not None
        }
        last_run_by_project = {p["id"]: p.get("last_processed_run_id") for p in projects}
        for proj_id, art_id in artifact_keys:
            session.add(Artifact(
                id=art_id,
                github_artifact_id=f"sync-{art_id}",
                project_id=proj_id,
                github_run_id=last_run_by_project.get(proj_id),
                status="processed",
                created_at=datetime.now(UTC),
            ))
        await session.commit()
        print(f"  inserted {len(artifact_keys)} synthetic artifact row(s)")

        # 5) findings — preserve id + artifact_id.
        #
        # JSON columns (raw_data, ai_analysis): SQLAlchemy's default JSON
        # type serializes Python None as the literal string "null" rather
        # than SQL NULL. Downstream `count_ai_analyzed` checks `IS NOT NULL`
        # so a string "null" inflates the count to 100%. We omit the kwarg
        # when the source is None so the column default (SQL NULL) wins.
        for f in all_findings:
            kwargs: dict[str, Any] = dict(
                id=f["id"],
                artifact_id=f["artifact_id"],
                tool=f["tool"],
                rule_id=f["rule_id"],
                severity=f["severity"],
                message=f["message"],
                file_path=f["file_path"],
                line_number=f.get("line_number"),
                normalized_at=datetime.fromisoformat(f["normalized_at"])
                if f.get("normalized_at") else None,
                cwe_id=f.get("cwe_id"),
                cvss_score=f.get("cvss_score"),
                dedup_hash=f.get("dedup_hash"),
                status=f.get("status", "pending_review"),
                justification=f.get("justification"),
                approved_by=f.get("approved_by"),
                approved_at=datetime.fromisoformat(f["approved_at"])
                if f.get("approved_at") else None,
                revoke_justification=f.get("revoke_justification"),
                revoked_by=f.get("revoked_by"),
                revoked_at=datetime.fromisoformat(f["revoked_at"])
                if f.get("revoked_at") else None,
            )
            if f.get("raw_data") is not None:
                kwargs["raw_data"] = f["raw_data"]
            if f.get("ai_analysis") is not None:
                kwargs["ai_analysis"] = f["ai_analysis"]
            session.add(Finding(**kwargs))
        await session.commit()
        print(f"  inserted {len(all_findings)} finding row(s)")

    print("\n=== Done ===")
    print("Restart local MCP (`uvicorn src.main:app --reload --port 8000`)")
    print("Dashboard at http://localhost:5173 should now mirror Render.")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default=os.environ.get("RENDER_MCP_URL", DEFAULT_URL))
    ap.add_argument("--apply", action="store_true",
                    help="Actually wipe + insert. Without this it's dry-run.")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    await sync(args.url, args.apply)


if __name__ == "__main__":
    asyncio.run(main())

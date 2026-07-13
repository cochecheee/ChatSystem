from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import delete, func as sql_func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..core.db import AsyncSessionLocal
from ..core.guardrails import ScrubbingService
from ..core.profiles import ArtifactProfile, load_profile
from ..models.entities import Artifact, Finding
from ..models.schemas import compute_dedup_hash
from .enricher import DataEnricher
from .github_client import GitHubClient
from .normalizers import NormalizerFactory

log = logging.getLogger(__name__)


def _is_security_artifact(name: str, profile: ArtifactProfile | None = None) -> bool:
    """Check whether a workflow artifact name matches the configured profile.

    The profile is loaded once per process (LRU-cached). Passing an explicit
    profile is intended for Day 2 (per-`Project` profile lookup).
    """
    return (profile or load_profile()).matches(name)


class SecurityProcessor:
    """Orchestrates the full pipeline: fetch → scrub → normalize → enrich → store."""

    def __init__(
        self,
        session_factory: async_sessionmaker | None = None,
        github_client: GitHubClient | None = None,
        scrubber: ScrubbingService | None = None,
        enricher: DataEnricher | None = None,
    ) -> None:
        self.session_factory = session_factory or AsyncSessionLocal
        self.github_client = github_client or GitHubClient()
        self.scrubber = scrubber or ScrubbingService()
        self.enricher = enricher or DataEnricher()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_artifact(
        self,
        db_artifact_id: int,
        github_artifact_id: int,
        gh: GitHubClient | None = None,
    ) -> int:
        """Fetch, scrub, normalize, enrich, and store findings for one artifact.

        Returns the number of findings stored. Pass `gh` to use a
        per-project client (Day 2 multi-tenant); omitted falls back to
        the default singleton.
        """
        async with self.session_factory() as session:
            return await self._run(session, db_artifact_id, github_artifact_id, gh)

    async def process_run(
        self,
        project_id: int,
        github_run_id: int,
        project=None,
    ) -> None:
        """Fetch security artifacts from a GitHub workflow run and process each one.

        Routing (V2.8 B2):
          - Background task được spawn từ webhook handler chỉ pass project_id
            (tránh detached ORM instance khi request session closed). Method
            tự fetch Project bằng id và xây per-project GitHubClient nếu có
            credentials.
          - Poller flow có thể pass `project` ORM object trực tiếp (đang
            trong session) — short-circuit lookup.
          - Project thiếu credentials (github_token/owner/repo trống) →
            fallback `self.github_client` (env-bound, single-tenant).
        """
        from ..models.entities import Artifact as ArtifactModel
        from ..models.entities import Project as ProjectModel

        if project is None:
            async with self.session_factory() as session:
                project = await session.get(ProjectModel, project_id)
                # Detach để dùng ngoài session (read-only access vào field)
                if project is not None:
                    session.expunge(project)

        # Route to the project's OWN repo whenever owner+repo are known — a
        # per-project token is NOT required. GitHubClient.for_project falls
        # back to the env GITHUB_TOKEN for auth (public repos work even
        # unauthenticated), so keying on github_token here was a bug: a
        # tokenless multi-tenant project (e.g. a public repo) silently fell
        # back to the ENV repo and fetched the WRONG run → 404 → 0 findings
        # (which wiped that project's data on reprocess).
        if project is not None and project.github_owner and project.github_repo:
            gh = GitHubClient.for_project(project)
            profile = load_profile(project.artifact_profile or None)
            log.info(
                "process_run %d: using repo %s/%s (token=%s)",
                github_run_id, project.github_owner, project.github_repo,
                "per-project" if project.github_token else "env-fallback",
            )
        else:
            gh = self.github_client
            profile = load_profile()
            log.info(
                "process_run %d: using env-bound GitHub client (project has no owner/repo)",
                github_run_id,
            )

        all_artifacts = await gh.list_artifacts(github_run_id)
        security_artifacts = [
            a for a in all_artifacts if _is_security_artifact(a.get("name", ""), profile)
        ]
        log.info(
            "Run %d: %d/%d artifacts are security-relevant",
            github_run_id, len(security_artifacts), len(all_artifacts),
        )

        processed_count = 0
        failed_count = 0
        for gh_artifact in security_artifacts:
            gh_artifact_id = str(gh_artifact["id"])
            async with self.session_factory() as session:
                # Idempotency: SAST and DAST webhooks land separately but
                # both call process_run with the same run_id; list_artifacts
                # returns the cumulative set on each call, so without this
                # check we'd recreate Artifact rows + duplicate Findings on
                # every overlapping webhook (or workflow rerun).
                existing = await session.execute(
                    select(ArtifactModel).where(
                        ArtifactModel.project_id == project_id,
                        ArtifactModel.github_artifact_id == gh_artifact_id,
                    )
                )
                db_artifact = existing.scalar_one_or_none()
                if db_artifact is not None and db_artifact.status == "processed":
                    log.info(
                        "Skipping artifact %s — already processed (db_id=%d)",
                        gh_artifact_id, db_artifact.id,
                    )
                    continue
                if db_artifact is None:
                    db_artifact = ArtifactModel(
                        github_artifact_id=gh_artifact_id,
                        project_id=project_id,
                        github_run_id=github_run_id,
                        status="pending",
                    )
                    session.add(db_artifact)
                    await session.commit()
                    await session.refresh(db_artifact)
                else:
                    # BUG-5 fix — artifact row exists but isn't 'processed'
                    # (status='pending' or 'failed' from a crashed prior run).
                    # Re-running _run on it would APPEND findings on top of the
                    # half-written set, producing duplicates. Wipe its findings
                    # first so the next pass is a clean re-ingest.
                    from sqlalchemy import delete as _sql_delete

                    from ..models.entities import Finding as FindingModel
                    await session.execute(
                        _sql_delete(FindingModel).where(
                            FindingModel.artifact_id == db_artifact.id,
                        )
                    )
                    await session.commit()
                    log.info(
                        "Cleaning stale findings for artifact %s (db_id=%d, status=%s) before retry",
                        gh_artifact_id, db_artifact.id, db_artifact.status,
                    )

            # BUG-4 fix — isolate per-artifact failures. One broken zip or a
            # normalizer crash on a single SARIF file must not stop the rest
            # of the run. Log + count, then continue.
            try:
                await self.process_artifact(db_artifact.id, gh_artifact["id"], gh=gh)
                processed_count += 1
            except Exception as exc:
                failed_count += 1
                log.error(
                    "process_run %d: artifact %s crashed — %s. Continuing with rest of run.",
                    github_run_id, gh_artifact_id, exc,
                )

        # BUG-1 fix — webhook path also bumps last_processed_run_id so the UI
        # and /projects API reflect the most recent ingest. Previously only
        # the poller did this, so webhook-driven runs left the field at None.
        # Only advance forward (never rewrite older run as latest).
        if processed_count > 0:
            async with self.session_factory() as session:
                db_proj = await session.get(ProjectModel, project_id)
                if db_proj is not None:
                    current = db_proj.last_processed_run_id or 0
                    if github_run_id > current:
                        db_proj.last_processed_run_id = github_run_id
                        await session.commit()

        # V3.8 Option A — current-state storage. After ingesting the newest
        # run, drop findings from OLDER runs of this project so the DB holds
        # only the latest scan per project (no per-run duplication → stored
        # data, dashboard KPIs, and the Vulns/SCA/DAST lists all agree at the
        # source, not just via query-time latest_run_only scoping). Guarded to
        # skip when reprocessing an OLD run so we never wipe newer data.
        if processed_count > 0:
            await self._prune_superseded_findings(project_id, github_run_id)
            # V3.9 — collapse merged-vs-per-tool duplicates WITHIN the kept run so
            # gate-count, KPIs, the Vulns/SCA/DAST lists and the AI summary all
            # count the same de-duplicated rows (one source of truth).
            await self._dedup_run_findings(project_id, github_run_id)
            # V4.0 — cross-tool correlation: collapse the SAME vulnerability
            # reported by different tools (Semgrep/CodeQL/Trivy…) into one
            # canonical row, recording the corroborating tools on the keeper.
            # Runs AFTER exact-hash dedup so it clusters already-unique rows.
            await self._correlate_run_findings(project_id, github_run_id)

        log.info(
            "process_run %d done — %d processed, %d failed (out of %d security artifacts)",
            github_run_id, processed_count, failed_count, len(security_artifacts),
        )

    async def _prune_superseded_findings(
        self, project_id: int, keep_github_run_id: int,
    ) -> int:
        """Delete findings belonging to runs OLDER than keep_github_run_id for
        this project — current-state storage (V3.8 Option A).

        Guard: only prune when keep_github_run_id is the newest run for the
        project (GitHub run ids increase monotonically). Reprocessing an old
        run must NOT delete the newer run's findings.

        Keeps Artifact + PipelineRun rows (run metadata / history) intact —
        only the duplicated Finding rows (and any CommandFeedback pointing at
        them) are removed. Returns the number of findings deleted.
        """
        from ..models.entities import Artifact as ArtifactModel
        from ..models.entities import CommandFeedback as FeedbackModel
        from ..models.entities import Finding as FindingModel

        async with self.session_factory() as session:
            newest = (await session.execute(
                select(sql_func.max(ArtifactModel.github_run_id)).where(
                    ArtifactModel.project_id == project_id,
                    ArtifactModel.github_run_id.is_not(None),
                )
            )).scalar_one_or_none() or 0
            if keep_github_run_id < newest:
                log.info(
                    "Prune skipped: run %d is older than newest %d for project %d",
                    keep_github_run_id, newest, project_id,
                )
                return 0

            old_artifact_ids = [
                r[0] for r in (await session.execute(
                    select(ArtifactModel.id).where(
                        ArtifactModel.project_id == project_id,
                        ArtifactModel.github_run_id.is_not(None),
                        ArtifactModel.github_run_id != keep_github_run_id,
                    )
                )).all()
            ]
            if not old_artifact_ids:
                return 0

            old_finding_ids = [
                r[0] for r in (await session.execute(
                    select(FindingModel.id).where(
                        FindingModel.artifact_id.in_(old_artifact_ids)
                    )
                )).all()
            ]
            if not old_finding_ids:
                return 0

            # FK order: feedback (finding_id, no cascade) → findings.
            await session.execute(
                delete(FeedbackModel).where(
                    FeedbackModel.finding_id.in_(old_finding_ids)
                )
            )
            result = await session.execute(
                delete(FindingModel).where(
                    FindingModel.id.in_(old_finding_ids)
                )
            )
            await session.commit()
            deleted = result.rowcount or len(old_finding_ids)
            log.info(
                "Pruned %d superseded findings from %d older-run artifact(s) "
                "(project %d, kept run %d)",
                deleted, len(old_artifact_ids), project_id, keep_github_run_id,
            )
            return deleted

    async def _dedup_run_findings(
        self, project_id: int, keep_github_run_id: int,
    ) -> int:
        """Collapse findings duplicated WITHIN one run to a single row per
        dedup_hash — current-state storage (V3.9).

        Root cause of CI↔dashboard number mismatch: a run publishes BOTH a
        merged artifact (`sast-reports-<run>`) AND per-tool artifacts
        (`sast-reports-<run>-<tool>`). process_run ingests every security
        artifact, so the SAME finding is stored once per artifact (raw ≈ 2×
        unique, ~3× when the poller re-ingests). `_prune_superseded_findings`
        only drops OLDER runs, never this within-run duplication — so
        `/findings/gate-count`, the latest-scan KPIs, the Vulns/SCA/DAST lists
        and the AI summary each counted inflated, disagreeing numbers.
        De-duping at the storage layer makes every surface agree at the source.

        For each dedup_hash group in the kept run, keep ONE row by priority —
        a decided triage status (APPROVED/REVOKED) first so audited decisions
        survive, then ai_analyzed (keeps the AI write-up), else the lowest id —
        re-point the audit children (finding_actions, command_feedback) of the
        dropped duplicates onto the keeper, then delete the duplicates. Returns
        the number of findings deleted.

        Guarded like _prune: only runs when keep_github_run_id is the project's
        newest run, so reprocessing an old run never disturbs newer data.
        """
        from collections import defaultdict

        from ..models.entities import Artifact as ArtifactModel
        from ..models.entities import CommandFeedback as FeedbackModel
        from ..models.entities import Finding as FindingModel
        from ..models.entities import FindingAction as ActionModel

        # Keeper priority (higher wins): audited decision > AI write-up > default.
        # Status strings match the app's constants (APPROVED/REVOKED are UPPER).
        _STATUS_PRIORITY = {"REVOKED": 3, "APPROVED": 3, "ai_analyzed": 2}

        async with self.session_factory() as session:
            newest = (await session.execute(
                select(sql_func.max(ArtifactModel.github_run_id)).where(
                    ArtifactModel.project_id == project_id,
                    ArtifactModel.github_run_id.is_not(None),
                )
            )).scalar_one_or_none() or 0
            if keep_github_run_id < newest:
                log.info(
                    "Dedup skipped: run %d is older than newest %d for project %d",
                    keep_github_run_id, newest, project_id,
                )
                return 0

            run_artifact_ids = [
                r[0] for r in (await session.execute(
                    select(ArtifactModel.id).where(
                        ArtifactModel.project_id == project_id,
                        ArtifactModel.github_run_id == keep_github_run_id,
                    )
                )).all()
            ]
            if not run_artifact_ids:
                return 0

            rows = (await session.execute(
                select(
                    FindingModel.id, FindingModel.dedup_hash, FindingModel.status,
                ).where(
                    FindingModel.artifact_id.in_(run_artifact_ids),
                    FindingModel.dedup_hash.is_not(None),
                )
            )).all()

            groups: dict[str, list[tuple[int, str]]] = defaultdict(list)
            for fid, dhash, status in rows:
                groups[dhash].append((fid, status))

            loser_ids: list[int] = []
            remap: dict[int, int] = {}
            for members in groups.values():
                if len(members) < 2:
                    continue
                # keeper: highest status priority, then lowest id (stable).
                keeper = max(
                    members,
                    key=lambda m: (_STATUS_PRIORITY.get(m[1], 1), -m[0]),
                )[0]
                for fid, _status in members:
                    if fid != keeper:
                        loser_ids.append(fid)
                        remap[fid] = keeper

            if not loser_ids:
                return 0

            # Re-point audit children of dropped duplicates so no history is lost.
            # At ingest time losers are brand-new (no children) → the SELECTs come
            # back empty and this is a no-op; for one-time cleanup of already-
            # triaged data it preserves the approve/revoke/feedback trail.
            for child in (ActionModel, FeedbackModel):
                referenced = {
                    r[0] for r in (await session.execute(
                        select(child.finding_id).where(
                            child.finding_id.in_(loser_ids),
                        )
                    )).all()
                }
                for loser in referenced:
                    await session.execute(
                        update(child).where(child.finding_id == loser).values(
                            finding_id=remap[loser],
                        )
                    )

            result = await session.execute(
                delete(FindingModel).where(FindingModel.id.in_(loser_ids))
            )
            await session.commit()
            deleted = result.rowcount or len(loser_ids)
            log.info(
                "Deduped %d within-run duplicate findings "
                "(project %d, run %d, %d unique kept)",
                deleted, project_id, keep_github_run_id, len(groups),
            )
            return deleted

    async def _correlate_run_findings(
        self, project_id: int, keep_github_run_id: int,
    ) -> int:
        """Cross-tool deduplication (V4.0) — collapse the SAME vulnerability
        reported by DIFFERENT tools into one canonical row.

        The exact-hash layers (`base.deduplicate`, `_dedup_run_findings`,
        Tier-1 carry-forward) key on `sha256(rule_id:file_path:message)`, so a
        SQL-injection flagged by Semgrep, CodeQL AND Trivy is stored 3× — each
        tool emits a different rule_id/message. That inflates gate-count, the
        KPIs and the Vulns/SCA lists (~2–3×) and hides the fact that several
        independent tools agree (a strong confidence signal).

        This step clusters the run's SURVIVING findings by a strict semantic
        key — same category (SAST/deps/DAST never mixed) + normalized file +
        CWE + a small line window — then keeps ONE row per cluster and deletes
        the rest (destructive collapse, so every count downstream is deduped at
        the source with no query changes). Findings without a parseable CWE are
        never cross-tool-merged (left as singletons). The corroborating tools of
        the dropped rows are preserved on the keeper's `raw_data['_correlation']`
        so the dashboard/terminal can show "found by N tools".

        Keeper priority (higher wins): audited decision (APPROVED/REVOKED) so
        triage survives, then AI write-up, then highest severity, then a
        precise-code-scanner preference, then lowest id (stable). Audit children
        (finding_actions, command_feedback) of dropped rows are re-pointed onto
        the keeper before deletion. Returns the number of findings deleted.

        Guarded like `_prune`/`_dedup`: only runs when keep_github_run_id is the
        project's newest run, so reprocessing an old run never disturbs newer
        data. Line window is tunable via DEDUP_LINE_WINDOW (default 5).
        """
        import os
        from collections import defaultdict

        from ..models.entities import Artifact as ArtifactModel
        from ..models.entities import CommandFeedback as FeedbackModel
        from ..models.entities import Finding as FindingModel
        from ..models.entities import FindingAction as ActionModel
        from ..repositories.finding_repo import DAST_TOOLS, DEPS_TOOLS

        window = max(1, int(os.getenv("DEDUP_LINE_WINDOW", "5") or 5))

        _SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
        _STATUS_PRIORITY = {"REVOKED": 3, "APPROVED": 3, "ai_analyzed": 2}
        _TOOL_PRIORITY = {
            "codeql": 6, "semgrep": 5,
            "spotbugs": 4, "bandit": 4, "gosec": 4,
            "eslint": 3,
            "npm-audit": 2, "safety": 2, "dependency-check": 2,
            "owasp-dependency-check": 2,
            "trivy": 1, "trivy-deps": 1, "owasp-zap": 1, "zap": 1,
        }

        def _category(tool: str) -> str:
            t = (tool or "").lower()
            if t in DEPS_TOOLS:
                return "deps"
            if t in DAST_TOOLS:
                return "dast"
            return "sast"

        def _norm_path(p: str | None) -> str:
            s = (p or "").strip().replace("\\", "/").lower()
            while s.startswith("./"):
                s = s[2:]
            return s

        def _cwe_num(cwe_id: str | None) -> int | None:
            if not cwe_id:
                return None
            digits = cwe_id.upper().replace("CWE-", "").strip()
            return int(digits) if digits.isdigit() else None

        async with self.session_factory() as session:
            newest = (await session.execute(
                select(sql_func.max(ArtifactModel.github_run_id)).where(
                    ArtifactModel.project_id == project_id,
                    ArtifactModel.github_run_id.is_not(None),
                )
            )).scalar_one_or_none() or 0
            if keep_github_run_id < newest:
                log.info(
                    "Correlate skipped: run %d is older than newest %d for project %d",
                    keep_github_run_id, newest, project_id,
                )
                return 0

            run_artifact_ids = [
                r[0] for r in (await session.execute(
                    select(ArtifactModel.id).where(
                        ArtifactModel.project_id == project_id,
                        ArtifactModel.github_run_id == keep_github_run_id,
                    )
                )).all()
            ]
            if not run_artifact_ids:
                return 0

            rows = (await session.execute(
                select(
                    FindingModel.id, FindingModel.tool, FindingModel.rule_id,
                    FindingModel.severity, FindingModel.cwe_id,
                    FindingModel.file_path, FindingModel.line_number,
                    FindingModel.message, FindingModel.status,
                    FindingModel.ai_analysis, FindingModel.raw_data,
                ).where(FindingModel.artifact_id.in_(run_artifact_ids))
            )).all()

            groups: dict[str, list[dict]] = defaultdict(list)
            for (fid, tool, rule_id, severity, cwe_id, file_path,
                 line_number, message, status, ai_analysis, raw_data) in rows:
                cwe = _cwe_num(cwe_id)
                if cwe is None:
                    continue  # no CWE → never cross-tool-merged
                bucket = str(line_number // window) if line_number is not None else "na"
                key = f"{_category(tool)}|{_norm_path(file_path)}|CWE-{cwe}|{bucket}"
                groups[key].append({
                    "id": fid, "tool": tool, "rule_id": rule_id,
                    "severity": severity, "cwe": f"CWE-{cwe}",
                    "line_number": line_number, "message": message,
                    "status": status, "has_ai": 1 if ai_analysis is not None else 0,
                    "raw_data": raw_data,
                })

            loser_ids: list[int] = []
            remap: dict[int, int] = {}
            clusters_collapsed = 0
            for key, members in groups.items():
                if len(members) < 2:
                    continue
                keeper = max(members, key=lambda m: (
                    _STATUS_PRIORITY.get(m["status"], 1),
                    _SEV_RANK.get((m["severity"] or "").lower(), 0),
                    m["has_ai"],
                    _TOOL_PRIORITY.get((m["tool"] or "").lower(), 1),
                    -m["id"],
                ))
                losers = [m for m in members if m["id"] != keeper["id"]]
                tools = sorted({m["tool"] for m in members if m["tool"]})
                sev_max = max(
                    members, key=lambda m: _SEV_RANK.get((m["severity"] or "").lower(), 0),
                )["severity"]
                correlation = {
                    "cluster_key": key,
                    "size": len(members),
                    "tools": tools,
                    "primary_tool": keeper["tool"],
                    "cwe": keeper["cwe"],
                    "severity_max": sev_max,
                    "members": [
                        {
                            "finding_id": m["id"], "tool": m["tool"],
                            "rule_id": m["rule_id"], "severity": m["severity"],
                            "line_number": m["line_number"],
                            "message": (m["message"] or "")[:300],
                        }
                        for m in losers
                    ],
                }
                # Reassign a fresh dict so the JSON column is marked dirty.
                new_raw = dict(keeper["raw_data"] or {})
                new_raw["_correlation"] = correlation
                await session.execute(
                    update(FindingModel).where(FindingModel.id == keeper["id"]).values(
                        raw_data=new_raw,
                    )
                )
                clusters_collapsed += 1
                for m in losers:
                    loser_ids.append(m["id"])
                    remap[m["id"]] = keeper["id"]

            if not loser_ids:
                return 0

            # Re-point audit children of dropped duplicates onto the keeper so
            # no approve/revoke/feedback history is lost. At ingest time losers
            # are brand-new (no children) → no-op; matters for one-time cleanup.
            for child in (ActionModel, FeedbackModel):
                referenced = {
                    r[0] for r in (await session.execute(
                        select(child.finding_id).where(
                            child.finding_id.in_(loser_ids),
                        )
                    )).all()
                }
                for loser in referenced:
                    await session.execute(
                        update(child).where(child.finding_id == loser).values(
                            finding_id=remap[loser],
                        )
                    )

            result = await session.execute(
                delete(FindingModel).where(FindingModel.id.in_(loser_ids))
            )
            await session.commit()
            deleted = result.rowcount or len(loser_ids)
            log.info(
                "Cross-tool correlated %d duplicate findings across %d clusters "
                "(project %d, run %d)",
                deleted, clusters_collapsed, project_id, keep_github_run_id,
            )
            return deleted

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    async def _run(
        self,
        session: AsyncSession,
        db_artifact_id: int,
        github_artifact_id: int,
        gh: GitHubClient | None = None,
    ) -> int:
        artifact = await session.get(Artifact, db_artifact_id)
        if artifact is None:
            raise ValueError(f"Artifact {db_artifact_id} not found in database")

        client = gh or self.github_client
        try:
            files = await client.fetch_artifact(github_artifact_id)
            db_findings = self._build_findings(files, db_artifact_id, artifact.project_id)

            # V3.1 Tier 1 — cross-run auto-revoke by dedup_hash match.
            # V3.1 Tier 2 — pattern-based auto-revoke from suppression_rules.
            # Tier 1 wins when both match (more specific = exact hash).
            from ..repositories.finding_repo import FindingRepository
            from ..repositories.suppression_repo import (
                SuppressionRuleRepository,
                rule_matches,
            )
            repo = FindingRepository(session)
            sup_repo = SuppressionRuleRepository(session)
            hashes = {f.dedup_hash for f in db_findings if f.dedup_hash}
            project_id = artifact.project_id
            prior = await repo.find_revoked_hashes(hashes, project_id=project_id)
            prior_appr = await repo.find_approved_hashes(hashes, project_id=project_id)
            active_rules = await sup_repo.list_active_for_project(project_id)
            auto_count_t1 = 0
            auto_count_t2 = 0
            auto_count_appr = 0
            for f in db_findings:
                if f.dedup_hash and f.dedup_hash in prior:
                    p = prior[f.dedup_hash]
                    f.status = "REVOKED"
                    f.revoked_by = "auto-suppress"
                    f.revoke_justification = (
                        f"Auto-suppressed (V3.1 Tier 1): inherited revoke from "
                        f"{p['revoked_by']!r} — {p['revoke_justification']}"
                    )
                    f.revoked_at = datetime.now(UTC)
                    auto_count_t1 += 1
                    continue
                # Tier 1 (approve) — carry forward an accepted-risk APPROVE so
                # the gate does NOT re-flag it next run. §5.2.5 / §4.2.3.
                if f.dedup_hash and f.dedup_hash in prior_appr:
                    p = prior_appr[f.dedup_hash]
                    f.status = "APPROVED"
                    f.approved_by = p["approved_by"] or "auto-approve"
                    f.justification = (
                        f"Auto-carried approval (V3.1 Tier 1): inherited APPROVE "
                        f"from {p['approved_by']!r} — {p['justification']}"
                    )
                    f.approved_at = datetime.now(UTC)
                    auto_count_appr += 1
                    continue
                for rule in active_rules:
                    if rule_matches(
                        rule,
                        finding_rule_id=f.rule_id,
                        finding_file_path=f.file_path,
                        finding_tool=f.tool,
                        finding_severity=f.severity,
                    ):
                        f.status = "REVOKED"
                        f.revoked_by = f"auto-suppress (rule #{rule.id})"
                        f.revoke_justification = (
                            f"Auto-suppressed (V3.1 Tier 2 rule #{rule.id} by "
                            f"{rule.created_by}): {rule.reason}"
                        )
                        f.revoked_at = datetime.now(UTC)
                        auto_count_t2 += 1
                        break
            auto_count = auto_count_t1 + auto_count_t2 + auto_count_appr

            session.add_all(db_findings)
            await session.flush()  # assign finding PKs before writing audit rows

            # §4.3.3 audit trail — the CI/CD pipeline (webhook → process_run) is
            # a state-changing source. Every auto-carried REVOKE/APPROVE decision
            # is recorded in finding_actions with submitted_by=webhook:<token-id>
            # so pipeline-driven triage is distinguishable from dashboard:/mcp:
            # actions in the immutable audit log.
            from ..models.entities import FindingAction
            for f in db_findings:
                if f.status == "REVOKED" and str(f.revoked_by or "").startswith("auto-suppress"):
                    session.add(FindingAction(
                        finding_id=f.id, action="revoke",
                        submitted_by="webhook:auto-triage",
                        detail=(f.revoke_justification or "")[:1000],
                    ))
                elif f.status == "APPROVED" and (f.justification or "").startswith("Auto-carried approval"):
                    session.add(FindingAction(
                        finding_id=f.id, action="approve",
                        submitted_by="webhook:auto-triage",
                        detail=(f.justification or "")[:1000],
                    ))

            artifact.status = "processed"
            await session.commit()

            log.info(
                "Stored %d findings for artifact %d (auto-triaged %d: %d revoke-hash, %d rule, %d approve-hash)",
                len(db_findings), db_artifact_id, auto_count, auto_count_t1, auto_count_t2, auto_count_appr,
            )
            return len(db_findings)

        except Exception as exc:
            # Transactional ingest — any failure mid-pipeline (fetch, normalize,
            # or the findings commit itself) rolls the whole unit of work back so
            # NO half-written findings are persisted. Then mark the artifact
            # 'failed' in a fresh, clean transaction. Without the rollback, a
            # failure during commit() could leave the session in a poisoned
            # state and the subsequent status write would raise (or worse,
            # partially commit).
            await session.rollback()
            stale = await session.get(Artifact, db_artifact_id)
            if stale is not None:
                stale.status = "failed"
                await session.commit()
            log.error("Failed to process artifact %d: %s", db_artifact_id, exc)
            raise

    def _build_findings(
        self,
        files: list[dict[str, str]],
        db_artifact_id: int,
        project_id: int | None = None,
    ) -> list[Finding]:
        batch_hashes: set[str] = set()
        results: list[Finding] = []

        for file_info in files:
            filename = file_info["filename"]
            scrubbed = self.scrubber.scrub_content(file_info["content"])

            try:
                normalizer = NormalizerFactory.get(filename, content=scrubbed)
            except ValueError as exc:
                log.info("Skipping %s — %s", filename, exc)
                continue

            try:
                findings = normalizer.normalize(scrubbed, artifact_id=db_artifact_id)
            except Exception as exc:
                log.warning("Failed to normalize %s: %s — skipping this file", filename, exc)
                continue

            log.info(
                "%s: %d findings normalized by %s",
                filename, len(findings), type(normalizer).__name__,
            )

            findings = normalizer.deduplicate(findings, existing_hashes=batch_hashes)

            for schema_finding in findings:
                enriched = self.enricher.enrich(schema_finding)
                # V2.7 — scrub PII trên message POST-parse. scrub_content
                # pre-parse từng break JSON escape (Issue: codeql.sarif silent
                # drop). Per-field scrub đảm bảo email/IP không lọt vào DB +
                # JSON SARIF vẫn parse được.
                scrubbed_message = self.scrubber.scrub_text(enriched.message)
                h = compute_dedup_hash(
                    enriched.rule_id, enriched.file_path, scrubbed_message
                )
                batch_hashes.add(h)

                results.append(
                    Finding(
                        artifact_id=db_artifact_id,
                        project_id=project_id,
                        tool=enriched.tool,
                        rule_id=enriched.rule_id,
                        severity=enriched.severity,
                        message=scrubbed_message,
                        file_path=enriched.file_path,
                        line_number=enriched.line_number,
                        raw_data=enriched.raw_data,
                        cwe_id=enriched.cwe_id,
                        cvss_score=enriched.cvss_score,
                        dedup_hash=h,
                        normalized_at=datetime.now(UTC),
                    )
                )

        return results

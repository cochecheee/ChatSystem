"""SARIF 2.1.x normalizer — Semgrep, CodeQL, SpotBugs/.sarif, ESLint/.sarif, Trivy/.sarif."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from ...models.schemas import FindingCreate, compute_dedup_hash
from .base import BaseNormalizer
from .severity import (
    _SARIF_LEVEL_TO_SEVERITY,
    _UPPERCASE_TO_SEVERITY,
    _security_severity_to_label,
)

log = logging.getLogger(__name__)

_TOOL_NAME_NORMALIZE: dict[str, str] = {
    # Map common SARIF driver names → canonical lowercase tool names so the
    # frontend can group/filter consistently.
    "semgrep":           "semgrep",
    "codeql":            "codeql",
    "codeql command-line tools": "codeql",
    "spotbugs":          "spotbugs",
    "find security bugs": "spotbugs",
    "eslint":            "eslint",
    "trivy":             "trivy",
    "aqua security trivy": "trivy",
}


def _normalize_tool_name(raw: str | None) -> str:
    if not raw:
        return "unknown"
    key = raw.strip().lower()
    return _TOOL_NAME_NORMALIZE.get(key, key)


class SarifNormalizer(BaseNormalizer):
    """Lenient SARIF parser — walks JSON dict so any SARIF 2.1.x variant works.

    The previous pydantic-based parser rejected SARIF reports from CodeQL and
    Semgrep that included extra fields not in sarif_pydantic's strict schema,
    causing those tools' findings to silently disappear.
    """

    TOOL_NAME = "sarif"

    def normalize(self, content: str, artifact_id: int) -> list[FindingCreate]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            log.warning("Invalid SARIF JSON: %s", exc)
            return []

        if not isinstance(data, dict):
            return []

        findings: list[FindingCreate] = []
        for run in data.get("runs") or []:
            if not isinstance(run, dict):
                continue
            tool_name = self._extract_tool_name(run)
            rules_index = self._index_rules(run)

            for result in run.get("results") or []:
                if not isinstance(result, dict):
                    continue
                # SARIF spec: level="none" means the result is NOT a problem
                # (informational metric, suppressed kind, etc.). Skip — storing
                # these inflates info-tier counts with non-actionable entries.
                # We use the EFFECTIVE level (result.level → rule
                # defaultConfiguration.level) so a rule configured as "none"
                # is caught too. If `security-severity` overrides to a real
                # risk score, keep it (some tools mis-emit level=none).
                rule_def_for_none = rules_index.get(result.get("ruleId") or "") or {}
                if self._effective_level(result, rule_def_for_none) == "none":
                    props = result.get("properties") or {}
                    rule_props = rule_def_for_none.get("properties") or {}
                    has_override = False
                    for src in (props, rule_props):
                        if isinstance(src, dict) and src.get("security-severity"):
                            try:
                                if float(src["security-severity"]) > 0:
                                    has_override = True
                                    break
                            except (TypeError, ValueError):
                                pass
                    if not has_override:
                        continue
                try:
                    findings.append(
                        self._result_to_finding(
                            result, tool_name, rules_index, artifact_id
                        )
                    )
                except Exception as exc:
                    log.debug("Skipping malformed SARIF result: %s", exc)
                    continue

        return findings

    @staticmethod
    def _extract_tool_name(run: dict[str, Any]) -> str:
        tool = run.get("tool") or {}
        driver = tool.get("driver") if isinstance(tool, dict) else None
        if isinstance(driver, dict):
            return _normalize_tool_name(driver.get("name"))
        return "unknown"

    @staticmethod
    def _index_rules(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Build a {ruleId: rule_dict} index from the run's rule metadata.

        Per SARIF 2.1.0 rules live in two possible places:
          - `tool.driver.rules` — Semgrep, Bandit, Trivy, ESLint
          - `tool.extensions[].rules` — CodeQL packs ALL query metadata here
            and leaves `driver.rules` EMPTY. Indexing only the driver dropped
            every CodeQL rule's `security-severity` / `problem.severity` / CWE
            tags, collapsing those findings to `info`.

        Driver rules take precedence on an id collision (the driver is the
        canonical tool; extensions are supplementary).
        """
        tool = run.get("tool") or {}
        if not isinstance(tool, dict):
            return {}

        index: dict[str, dict[str, Any]] = {}

        # Extensions first; driver overwrites below on the rare id collision.
        for ext in tool.get("extensions") or []:
            if not isinstance(ext, dict):
                continue
            for r in ext.get("rules") or []:
                if isinstance(r, dict) and r.get("id"):
                    index.setdefault(r["id"], r)

        driver = tool.get("driver")
        if isinstance(driver, dict):
            for r in driver.get("rules") or []:
                if isinstance(r, dict) and r.get("id"):
                    index[r["id"]] = r

        return index

    def _result_to_finding(
        self,
        result: dict[str, Any],
        tool_name: str,
        rules_index: dict[str, dict[str, Any]],
        artifact_id: int,
    ) -> FindingCreate:
        rule_id = result.get("ruleId") or result.get("rule", {}).get("id") or "unknown-rule"
        rule_def = rules_index.get(rule_id) or {}
        # SARIF effective level (§3.27.10): explicit result.level wins, else
        # inherit the rule's defaultConfiguration.level, else spec default.
        level = self._effective_level(result, rule_def)
        severity = self._extract_severity(result, rule_def, level)

        msg_obj = result.get("message") or {}
        message = msg_obj.get("text") if isinstance(msg_obj, dict) else ""
        if not message:
            # Some SARIF reports put the human-readable text in markdown
            message = msg_obj.get("markdown", "") if isinstance(msg_obj, dict) else ""

        # Fall back to rule short description when result message is empty
        if not message:
            short = rule_def.get("shortDescription") or {}
            if isinstance(short, dict):
                message = short.get("text") or ""
        if not message:
            message = rule_id

        file_path, line_number = self._extract_location(result)
        cwe_id = self._extract_cwe(rule_def)

        dedup = compute_dedup_hash(rule_id, file_path, message)
        return FindingCreate(
            artifact_id=artifact_id,
            tool=tool_name,
            rule_id=rule_id,
            severity=severity,
            message=message,
            file_path=file_path,
            line_number=line_number,
            cwe_id=cwe_id,
            raw_data={
                "level": level,
                "dedup_hash": dedup,
            },
        )

    @staticmethod
    def _effective_level(result: dict[str, Any], rule_def: dict[str, Any]) -> str:
        """Resolve the SARIF effective level (§3.27.10).

        Order: explicit `result.level` → the matched rule's
        `defaultConfiguration.level` → spec default `"warning"`. Semgrep and
        Bandit omit `result.level` and encode the real severity ONLY in
        `defaultConfiguration.level` (error/warning/note), so without this
        inheritance every such finding collapsed to `info`.
        """
        lvl = result.get("level")
        if isinstance(lvl, str) and lvl.strip():
            return lvl.strip().lower()
        dc = rule_def.get("defaultConfiguration") or {}
        if isinstance(dc, dict):
            dlvl = dc.get("level")
            if isinstance(dlvl, str) and dlvl.strip():
                return dlvl.strip().lower()
        return "warning"  # SARIF spec default when level is unspecified

    @staticmethod
    def _extract_severity(
        result: dict[str, Any],
        rule_def: dict[str, Any],
        level: str,
    ) -> str:
        """Resolve severity using rule properties before falling back to SARIF `level`.

        CodeQL and Semgrep emit `level=error` for most security rules regardless
        of actual risk; the real severity lives in rule `properties`. Order:
          1. `security-severity` numeric (CVSS-style, GitHub-aligned thresholds)
          2. `problem.severity` (CodeQL: error|warning|recommendation)
          3. `properties.severity` (Semgrep: ERROR|WARNING|INFO, or CRITICAL/HIGH/...)
          4. SARIF `level` (error|warning|note|none)
        """
        # Result-level properties win over rule-level (some emitters override per finding)
        for src in (result.get("properties") or {}, rule_def.get("properties") or {}):
            if not isinstance(src, dict):
                continue
            raw_score = src.get("security-severity")
            if raw_score is not None:
                try:
                    return _security_severity_to_label(float(raw_score))
                except (TypeError, ValueError):
                    pass
            problem_sev = src.get("problem.severity")
            if isinstance(problem_sev, str) and problem_sev.strip():
                mapped = _UPPERCASE_TO_SEVERITY.get(problem_sev.strip().upper())
                if mapped:
                    return mapped
            prop_sev = src.get("severity")
            if isinstance(prop_sev, str) and prop_sev.strip():
                mapped = _UPPERCASE_TO_SEVERITY.get(prop_sev.strip().upper())
                if mapped:
                    return mapped
        # `level` is the resolved effective level (error/warning/note/none).
        # An unrecognised level defaults to "medium" (pending triage), NOT
        # "info" — mirroring _sca_severity. Defaulting unknowns to the lowest
        # bucket silently under-rated real issues whose level didn't resolve.
        return _SARIF_LEVEL_TO_SEVERITY.get(level, "medium")

    @staticmethod
    def _extract_location(result: dict[str, Any]) -> tuple[str, int | None]:
        locations = result.get("locations") or []
        uri: str | None = None
        line: int | None = None

        if isinstance(locations, list) and locations:
            loc = locations[0]
            if isinstance(loc, dict):
                pl = loc.get("physicalLocation") or {}
                if isinstance(pl, dict):
                    artifact_loc = pl.get("artifactLocation") or {}
                    uri = artifact_loc.get("uri") if isinstance(artifact_loc, dict) else None
                    region = pl.get("region") or {}
                    line = region.get("startLine") if isinstance(region, dict) else None

        # Fallback: if primary location is empty/unknown, try relatedLocations[0]
        if not uri or uri == "unknown":
            related = result.get("relatedLocations") or []
            if isinstance(related, list) and related:
                rel = related[0]
                if isinstance(rel, dict):
                    pl2 = rel.get("physicalLocation") or {}
                    if isinstance(pl2, dict):
                        artifact_loc2 = pl2.get("artifactLocation") or {}
                        fb_uri = artifact_loc2.get("uri") if isinstance(artifact_loc2, dict) else None
                        if fb_uri:
                            uri = fb_uri
                        region2 = pl2.get("region") or {}
                        fb_line = region2.get("startLine") if isinstance(region2, dict) else None
                        if fb_line is not None:
                            line = fb_line

        return uri or "unknown", line

    @staticmethod
    def _extract_cwe(rule_def: dict[str, Any]) -> str | None:
        """Pull a CWE id out of rule properties / tags (CodeQL & Semgrep).

        Handles both tag conventions seen in the wild:
          - CodeQL:  "external/cwe/cwe-079"  (lives in extensions rules)
          - Semgrep: "CWE-89: Improper Neutralization ... ('SQL Injection')"
        A single regex `cwe[-/_ ]?(\\d+)` covers both; the previous parser only
        matched the CodeQL form, so Semgrep findings lost their CWE — which in
        turn disabled the CWE-based high→critical promotion for SAST.
        """
        if not rule_def:
            return None
        props = rule_def.get("properties") or {}
        if not isinstance(props, dict):
            return None
        tags = props.get("tags") or []
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, str):
                    m = re.search(r"cwe[-/_ ]?(\d+)", tag, re.IGNORECASE)
                    if m:
                        return f"CWE-{int(m.group(1))}"
        cwe = props.get("cwe")
        if isinstance(cwe, str) and cwe:
            m = re.search(r"(\d+)", cwe)
            if m:
                return f"CWE-{int(m.group(1))}"
        return None

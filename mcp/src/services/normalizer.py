from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import defusedxml.ElementTree as ET

from ..models.schemas import FindingCreate, compute_dedup_hash

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity mappings
# ---------------------------------------------------------------------------

_SARIF_LEVEL_TO_SEVERITY: dict[str, str] = {
    "error": "high",
    "warning": "medium",
    "note": "low",
    "none": "info",
}

_SPOTBUGS_PRIORITY_TO_SEVERITY: dict[str, str] = {
    "1": "high",
    "2": "medium",
    "3": "low",
    "4": "info",
    "5": "info",
}

_ESLINT_SEVERITY_TO_SEVERITY: dict[int, str] = {
    2: "high",
    1: "medium",
    0: "info",
}

_UPPERCASE_TO_SEVERITY: dict[str, str] = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    "UNKNOWN": "info",
    "INFO": "info",
    # Semgrep `properties.severity` variants
    "ERROR": "high",
    "WARNING": "medium",
    "INFORMATIONAL": "info",
    # CodeQL `properties["problem.severity"]` variants
    "RECOMMENDATION": "low",
}


def _security_severity_to_label(score: float) -> str:
    """Map CVSS-style numeric score (0–10) to severity bucket.

    Mirrors GitHub Advanced Security thresholds:
    https://docs.github.com/en/code-security/code-scanning/managing-code-scanning-alerts/about-code-scanning-alerts#about-alert-severity-and-security-severity-levels
    """
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    if score > 0:
        return "low"
    return "info"


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class BaseNormalizer(ABC):
    TOOL_NAME: str = "unknown"

    @abstractmethod
    def normalize(self, content: str, artifact_id: int) -> list[FindingCreate]:
        """Parse raw content and return normalised findings."""

    def deduplicate(
        self,
        findings: list[FindingCreate],
        existing_hashes: set[str],
    ) -> list[FindingCreate]:
        """Remove findings whose dedup hash already exists."""
        seen: set[str] = set()
        result: list[FindingCreate] = []
        for f in findings:
            h = compute_dedup_hash(f.rule_id, f.file_path, f.message)
            if h not in existing_hashes and h not in seen:
                seen.add(h)
                result.append(f)
        return result


# ---------------------------------------------------------------------------
# SARIF — Semgrep, CodeQL, SpotBugs .sarif, ESLint .sarif, Trivy .sarif
# ---------------------------------------------------------------------------

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
                try:
                    findings.append(
                        self._result_to_finding(
                            result, tool_name, rules_index, artifact_id
                        )
                    )
                except Exception as exc:  # noqa: BLE001 - skip individual result, keep going
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
        """Build a {ruleId: rule_dict} index from `tool.driver.rules` if present."""
        tool = run.get("tool") or {}
        driver = tool.get("driver") if isinstance(tool, dict) else None
        rules = driver.get("rules") if isinstance(driver, dict) else None
        if not isinstance(rules, list):
            return {}
        return {
            r.get("id"): r
            for r in rules
            if isinstance(r, dict) and r.get("id")
        }

    def _result_to_finding(
        self,
        result: dict[str, Any],
        tool_name: str,
        rules_index: dict[str, dict[str, Any]],
        artifact_id: int,
    ) -> FindingCreate:
        rule_id = result.get("ruleId") or result.get("rule", {}).get("id") or "unknown-rule"
        level = (result.get("level") or "none")
        rule_def = rules_index.get(rule_id) or {}
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
        return _SARIF_LEVEL_TO_SEVERITY.get(level, "info")

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
        """Try to pull a CWE id out of rule properties / tags (CodeQL & Semgrep)."""
        if not rule_def:
            return None
        props = rule_def.get("properties") or {}
        if not isinstance(props, dict):
            return None
        # CodeQL: properties.tags = ["external/cwe/cwe-079", ...]
        tags = props.get("tags") or []
        if isinstance(tags, list):
            for tag in tags:
                if isinstance(tag, str) and "cwe" in tag.lower():
                    parts = tag.lower().split("cwe-")
                    if len(parts) > 1 and parts[1][:4].rstrip("/").isdigit():
                        num = parts[1].split("/")[0]
                        return f"CWE-{int(num)}"
        cwe = props.get("cwe")
        if isinstance(cwe, str) and cwe:
            return cwe if cwe.startswith("CWE-") else f"CWE-{cwe}"
        return None


# ---------------------------------------------------------------------------
# SpotBugs XML
# ---------------------------------------------------------------------------

class SpotBugsXMLNormalizer(BaseNormalizer):
    TOOL_NAME = "spotbugs"

    def normalize(self, content: str, artifact_id: int) -> list[FindingCreate]:
        root = ET.fromstring(content)  # defusedxml — Billion Laughs safe
        findings: list[FindingCreate] = []

        for bug in root.iter("BugInstance"):
            rule_id = bug.get("type", "unknown")
            priority = bug.get("priority", "3")
            severity = _SPOTBUGS_PRIORITY_TO_SEVERITY.get(priority, "low")
            cwe_id = bug.get("cweid")
            cwe_str = f"CWE-{cwe_id}" if cwe_id else None

            short_msg = bug.findtext("ShortMessage") or bug.get("type", "")
            long_msg = bug.findtext("LongMessage") or short_msg
            message = long_msg or short_msg

            source = bug.find("SourceLine")
            if source is not None:
                file_path = source.get("sourcepath") or source.get("classname") or "unknown"
                line_str = source.get("start")
                line_number = int(line_str) if line_str and line_str.isdigit() else None
            else:
                file_path = "unknown"
                line_number = None

            dedup = compute_dedup_hash(rule_id, file_path, message)
            findings.append(
                FindingCreate(
                    artifact_id=artifact_id,
                    tool=self.TOOL_NAME,
                    rule_id=rule_id,
                    severity=severity,
                    message=message,
                    file_path=file_path,
                    line_number=line_number,
                    cwe_id=cwe_str,
                    raw_data={
                        "category": bug.get("category"),
                        "rank": bug.get("rank"),
                        "dedup_hash": dedup,
                    },
                )
            )

        return findings


# ---------------------------------------------------------------------------
# ESLint JSON (legacy format — pipeline hiện tại dùng .sarif nhưng giữ lại
# để hỗ trợ pipeline cũ hoặc custom formatter)
# ---------------------------------------------------------------------------

class ESLintNormalizer(BaseNormalizer):
    TOOL_NAME = "eslint"

    def normalize(self, content: str, artifact_id: int) -> list[FindingCreate]:
        data = json.loads(content)
        findings: list[FindingCreate] = []

        if not isinstance(data, list) or not data:
            return findings

        for file_result in data:
            if not isinstance(file_result, dict):
                continue
            file_path = file_result.get("filePath", "unknown")
            for msg in file_result.get("messages", []):
                rule_id = msg.get("ruleId") or "unknown-rule"
                eslint_sev = msg.get("severity", 1)
                severity = _ESLINT_SEVERITY_TO_SEVERITY.get(eslint_sev, "medium")
                message = msg.get("message", "")
                line_number = msg.get("line")

                dedup = compute_dedup_hash(rule_id, file_path, message)
                findings.append(
                    FindingCreate(
                        artifact_id=artifact_id,
                        tool=self.TOOL_NAME,
                        rule_id=rule_id,
                        severity=severity,
                        message=message,
                        file_path=file_path,
                        line_number=line_number,
                        raw_data={
                            "column": msg.get("column"),
                            "dedup_hash": dedup,
                        },
                    )
                )

        return findings


# ---------------------------------------------------------------------------
# OWASP Dependency-Check JSON  (dep-check-report artifact)
# ---------------------------------------------------------------------------

def _parse_purl_version(purl: str) -> str | None:
    """Extract version from a Package URL string: pkg:ecosystem/group/artifact@version"""
    match = re.search(r"@([^?#]+)", purl)
    return match.group(1) if match else None


class DepCheckNormalizer(BaseNormalizer):
    TOOL_NAME = "dependency-check"

    def normalize(self, content: str, artifact_id: int) -> list[FindingCreate]:
        data = json.loads(content)
        findings: list[FindingCreate] = []

        for dep in data.get("dependencies", []):
            file_path = dep.get("fileName") or dep.get("filePath") or "unknown"

            # Extract package version from PURL (packages[].id)
            pkg_name: str = dep.get("fileName", "")
            installed_version: str | None = None
            for pkg in dep.get("packages") or []:
                pkg_id = pkg.get("id", "")
                if pkg_id:
                    installed_version = _parse_purl_version(pkg_id)
                    break

            for vuln in dep.get("vulnerabilities", []):
                rule_id = vuln.get("name") or "unknown-cve"
                sev_raw = vuln.get("severity", "").upper()
                severity = _UPPERCASE_TO_SEVERITY.get(sev_raw, "medium")
                message = vuln.get("description") or rule_id
                cwes: list[str] = vuln.get("cwes") or []
                cwe_id = cwes[0] if cwes else None

                cvss_score: float | None = None
                if cvssv3 := vuln.get("cvssv3"):
                    cvss_score = cvssv3.get("baseScore")
                elif cvssv2 := vuln.get("cvssv2"):
                    cvss_score = cvssv2.get("score")

                dedup = compute_dedup_hash(rule_id, file_path, message)
                findings.append(
                    FindingCreate(
                        artifact_id=artifact_id,
                        tool=self.TOOL_NAME,
                        rule_id=rule_id,
                        severity=severity,
                        message=message,
                        file_path=file_path,
                        line_number=None,
                        cwe_id=cwe_id,
                        cvss_score=cvss_score,
                        raw_data={
                            "source": vuln.get("source"),
                            "pkg_name": pkg_name,
                            "installed_version": installed_version,
                            "fixed_version": None,  # DepCheck JSON does not include a fixed version
                            "dedup_hash": dedup,
                        },
                    )
                )

        return findings


# ---------------------------------------------------------------------------
# Trivy JSON  (trivy-image.json / trivy detailed container scan)
# ---------------------------------------------------------------------------

class TrivyJsonNormalizer(BaseNormalizer):
    TOOL_NAME = "trivy"

    def normalize(self, content: str, artifact_id: int) -> list[FindingCreate]:
        data = json.loads(content)
        findings: list[FindingCreate] = []

        for result_entry in data.get("Results", []):
            target = result_entry.get("Target", "unknown")

            for vuln in result_entry.get("Vulnerabilities") or []:
                rule_id = vuln.get("VulnerabilityID") or "unknown-cve"
                sev_raw = vuln.get("Severity", "").upper()
                severity = _UPPERCASE_TO_SEVERITY.get(sev_raw, "medium")
                message = vuln.get("Title") or vuln.get("Description") or rule_id
                cwe_ids: list[str] = vuln.get("CweIDs") or []
                cwe_id = cwe_ids[0] if cwe_ids else None

                cvss_score: float | None = None
                cvss = vuln.get("CVSS") or {}
                if nvd := cvss.get("nvd"):
                    cvss_score = nvd.get("V3Score") or nvd.get("V2Score")

                pkg_name = vuln.get("PkgName", "")
                file_path = f"{target}:{pkg_name}" if pkg_name else target

                dedup = compute_dedup_hash(rule_id, file_path, message)
                findings.append(
                    FindingCreate(
                        artifact_id=artifact_id,
                        tool=self.TOOL_NAME,
                        rule_id=rule_id,
                        severity=severity,
                        message=message,
                        file_path=file_path,
                        line_number=None,
                        cwe_id=cwe_id,
                        cvss_score=cvss_score,
                        raw_data={
                            "pkg_name": pkg_name,
                            "installed_version": vuln.get("InstalledVersion"),
                            "fixed_version": vuln.get("FixedVersion"),
                            "dedup_hash": dedup,
                        },
                    )
                )

        return findings


class ZapJsonNormalizer(BaseNormalizer):
    """OWASP ZAP baseline/full-scan JSON report — V2.3 DAST findings.

    ZAP riskcode mapping:  0=Informational  1=Low  2=Medium  3=High
    We emit 1 Finding per (alert, instance) so re-occurrences across
    URLs aren't lost. dedup hash uses (rule_id, uri, alert) so the same
    issue at the same URL collapses on rescan.
    """

    TOOL_NAME = "owasp-zap"
    _RISK_TO_SEVERITY: dict[str, str] = {
        "0": "info",
        "1": "low",
        "2": "medium",
        "3": "high",
    }

    def normalize(self, content: str, artifact_id: int) -> list[FindingCreate]:
        data = json.loads(content)
        findings: list[FindingCreate] = []

        for site in data.get("site") or []:
            site_url = site.get("@name", "")
            for alert in site.get("alerts") or []:
                rule_id = alert.get("pluginid") or alert.get("alertRef") or "zap-unknown"
                severity = self._RISK_TO_SEVERITY.get(
                    str(alert.get("riskcode", "")), "medium"
                )
                title = alert.get("alert") or alert.get("name") or rule_id
                description = alert.get("desc", "")
                solution = alert.get("solution", "")
                cwe_raw = alert.get("cweid")
                cwe_id = f"CWE-{cwe_raw}" if cwe_raw and cwe_raw != "-1" else None

                instances = alert.get("instances") or [{}]
                for inst in instances:
                    uri = inst.get("uri") or site_url
                    method = inst.get("method", "")
                    file_path = f"{method} {uri}".strip()
                    message = f"{title} — {description[:200]}".strip(" —")

                    dedup = compute_dedup_hash(rule_id, file_path, title)
                    findings.append(
                        FindingCreate(
                            artifact_id=artifact_id,
                            tool=self.TOOL_NAME,
                            rule_id=rule_id,
                            severity=severity,
                            message=message,
                            file_path=file_path,
                            line_number=None,
                            cwe_id=cwe_id,
                            cvss_score=None,
                            raw_data={
                                "alert": title,
                                "uri": uri,
                                "method": method,
                                "param": inst.get("param", ""),
                                "evidence": inst.get("evidence", ""),
                                "attack": inst.get("attack", ""),
                                "solution": solution,
                                "reference": alert.get("reference", ""),
                                "confidence": alert.get("confidence", ""),
                                "wascid": alert.get("wascid", ""),
                                "dedup_hash": dedup,
                            },
                        )
                    )

        return findings


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class NormalizerFactory:
    @staticmethod
    def get(filename: str, content: str | None = None) -> BaseNormalizer:
        ext = Path(filename).suffix.lower()
        if ext == ".sarif":
            return SarifNormalizer()
        if ext == ".xml":
            return SpotBugsXMLNormalizer()
        if ext == ".json":
            if content is None:
                # Backward compat for tests that don't supply content
                return ESLintNormalizer()
            return NormalizerFactory._detect_json(filename, content)
        raise ValueError(f"No normalizer for file type: {filename!r}")

    @staticmethod
    def _detect_json(filename: str, content: str) -> BaseNormalizer:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {filename!r}: {exc}") from exc

        if isinstance(data, dict):
            if "runs" in data:
                # SARIF spec stored as .json (valid SARIF JSON)
                return SarifNormalizer()
            if "dependencies" in data:
                # OWASP Dependency-Check JSON report
                return DepCheckNormalizer()
            if "Results" in data and "SchemaVersion" in data:
                # Trivy detailed JSON output
                return TrivyJsonNormalizer()
            if "site" in data and isinstance(data.get("site"), list):
                # OWASP ZAP baseline/full-scan JSON output (V2.3 DAST)
                return ZapJsonNormalizer()
            raise ValueError(
                f"Unrecognized JSON format in {filename!r} — "
                "not SARIF, Dependency-Check, Trivy, or ZAP; skipping"
            )

        if isinstance(data, list):
            return ESLintNormalizer()

        raise ValueError(f"Unexpected JSON structure in {filename!r}")

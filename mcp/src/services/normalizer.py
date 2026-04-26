from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path

import defusedxml.ElementTree as ET
from sarif_pydantic import Sarif

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
}


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

class SarifNormalizer(BaseNormalizer):
    TOOL_NAME = "sarif"

    def normalize(self, content: str, artifact_id: int) -> list[FindingCreate]:
        sarif = Sarif.model_validate_json(content)
        findings: list[FindingCreate] = []

        for run in sarif.runs or []:
            tool_name = (
                run.tool.driver.name
                if run.tool and run.tool.driver and run.tool.driver.name
                else "unknown"
            ).lower()

            for result in run.results or []:
                rule_id = result.rule_id or "unknown-rule"
                level = result.level.value if result.level else "none"
                severity = _SARIF_LEVEL_TO_SEVERITY.get(level, "info")
                message = (
                    result.message.text if result.message and result.message.text else ""
                )

                file_path, line_number = self._extract_location(result)

                dedup = compute_dedup_hash(rule_id, file_path, message)
                findings.append(
                    FindingCreate(
                        artifact_id=artifact_id,
                        tool=tool_name,
                        rule_id=rule_id,
                        severity=severity,
                        message=message,
                        file_path=file_path,
                        line_number=line_number,
                        raw_data={
                            "level": level,
                            "dedup_hash": dedup,
                        },
                    )
                )

        return findings

    @staticmethod
    def _extract_location(result) -> tuple[str, int | None]:
        locations = result.locations or []
        if not locations:
            return "unknown", None
        loc = locations[0]
        pl = loc.physical_location
        if not pl:
            return "unknown", None
        uri = pl.artifact_location.uri if pl.artifact_location else None
        line = pl.region.start_line if pl.region else None
        return uri or "unknown", line


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

class DepCheckNormalizer(BaseNormalizer):
    TOOL_NAME = "dependency-check"

    def normalize(self, content: str, artifact_id: int) -> list[FindingCreate]:
        data = json.loads(content)
        findings: list[FindingCreate] = []

        for dep in data.get("dependencies", []):
            file_path = dep.get("fileName") or dep.get("filePath") or "unknown"

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
            raise ValueError(
                f"Unrecognized JSON format in {filename!r} — "
                "not SARIF, Dependency-Check, or Trivy; skipping"
            )

        if isinstance(data, list):
            return ESLintNormalizer()

        raise ValueError(f"Unexpected JSON structure in {filename!r}")

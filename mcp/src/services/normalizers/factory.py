"""NormalizerFactory — dispatch a raw report to the right normalizer.

Routes by file extension first (.sarif / .xml / .json); for .json the shape is
introspected because many tools share the extension.
"""
from __future__ import annotations

import json
from pathlib import Path

from .base import BaseNormalizer
from .depcheck import DepCheckNormalizer
from .eslint import ESLintNormalizer
from .npm_audit import NpmAuditNormalizer
from .safety import SafetyJsonNormalizer
from .sarif import SarifNormalizer
from .spotbugs import SpotBugsXMLNormalizer
from .trivy import TrivyJsonNormalizer
from .zap import ZapJsonNormalizer


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
            if "auditReportVersion" in data or "advisories" in data or (
                isinstance(data.get("vulnerabilities"), dict) and "metadata" in data
            ):
                # `npm audit --json` (Node.js SCA) — v7+ (auditReportVersion 2)
                # or v6 (advisories). Previously dropped → Node dep CVEs vanished.
                return NpmAuditNormalizer()
            if isinstance(data.get("vulnerabilities"), list) or "affected_packages" in data:
                # `safety check --json` (Python SCA), modern dict shape
                return SafetyJsonNormalizer()
            raise ValueError(
                f"Unrecognized JSON format in {filename!r} — not SARIF, "
                "Dependency-Check, Trivy, ZAP, npm-audit, or Safety; skipping"
            )

        if isinstance(data, list):
            # safety v1 emits a list-of-lists ([pkg, spec, installed, advisory, id])
            # or list-of-dicts with package_name; ESLint emits dicts with filePath.
            if data and isinstance(data[0], (list, tuple)):
                return SafetyJsonNormalizer()
            if (data and isinstance(data[0], dict)
                    and "filePath" not in data[0]
                    and ("package_name" in data[0] or "advisory" in data[0])):
                return SafetyJsonNormalizer()
            return ESLintNormalizer()

        raise ValueError(f"Unexpected JSON structure in {filename!r}")

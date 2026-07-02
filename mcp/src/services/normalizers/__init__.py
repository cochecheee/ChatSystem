"""Security-tool report normalizers.

Each tool's parser lives in its own module (``sarif``, ``spotbugs``, ``trivy``,
``depcheck``, ``zap``, ``npm_audit``, ``safety``, ``eslint``); shared severity
tables/helpers live in ``severity`` and the common base class in ``base``.
``NormalizerFactory`` dispatches a raw report to the right parser.

Import the public surface from this package:

    from src.services.normalizers import NormalizerFactory, SarifNormalizer
"""
from __future__ import annotations

from .base import BaseNormalizer
from .depcheck import DepCheckNormalizer
from .eslint import ESLintNormalizer
from .factory import NormalizerFactory
from .npm_audit import NpmAuditNormalizer
from .safety import SafetyJsonNormalizer
from .sarif import SarifNormalizer
from .spotbugs import SpotBugsXMLNormalizer
from .trivy import TrivyJsonNormalizer
from .zap import ZapJsonNormalizer

__all__ = [
    "BaseNormalizer",
    "NormalizerFactory",
    "SarifNormalizer",
    "SpotBugsXMLNormalizer",
    "ESLintNormalizer",
    "DepCheckNormalizer",
    "TrivyJsonNormalizer",
    "ZapJsonNormalizer",
    "NpmAuditNormalizer",
    "SafetyJsonNormalizer",
]

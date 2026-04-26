from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.schemas import AnalysisResult
from src.services.llm.schemas import AnalysisOutput
from src.services.llm.service import LLMAnalysisService, _extract_context

SAMPLE_OUTPUT = AnalysisOutput(
    vulnerability_id="RULE-001",
    explanation_vi="Lỗ hổng SQL Injection do nối chuỗi trực tiếp.",
    impact_vi="Kẻ tấn công có thể đọc toàn bộ database.",
    remediation_diff="--- a/Dao.java\n+++ b/Dao.java\n@@ -5 +5 @@\n-query+input\n+preparedStatement",
    severity="HIGH",
    cwe_reference="CWE-89: SQL Injection",
    confidence="HIGH",
)


def _make_finding(status="pending_review", ai_analysis=None):
    f = MagicMock()
    f.id = 1
    f.tool = "semgrep"
    f.rule_id = "java.sqli"
    f.message = "SQL injection"
    f.file_path = "src/Dao.java"
    f.line_number = 10
    f.cwe_id = "CWE-89"
    f.cvss_score = 7.5
    f.raw_data = {}
    f.status = status
    f.ai_analysis = ai_analysis
    return f


@pytest.mark.asyncio
async def test_analyze_finding_returns_result():
    mock_client = AsyncMock()
    mock_client.analyze.return_value = SAMPLE_OUTPUT

    service = LLMAnalysisService(client=mock_client)
    finding = _make_finding()
    session = AsyncMock()

    result = await service.analyze_finding(finding, session)

    assert isinstance(result, AnalysisResult)
    assert result.finding_id == 1
    assert result.severity == "HIGH"
    assert "SQL" in result.explanation_vi


@pytest.mark.asyncio
async def test_analyze_finding_sets_status_and_saves():
    mock_client = AsyncMock()
    mock_client.analyze.return_value = SAMPLE_OUTPUT

    service = LLMAnalysisService(client=mock_client)
    finding = _make_finding()
    session = AsyncMock()

    await service.analyze_finding(finding, session)

    assert finding.status == "ai_analyzed"
    assert finding.ai_analysis is not None
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_finding_uses_code_context():
    mock_client = AsyncMock()
    mock_client.analyze.return_value = SAMPLE_OUTPUT

    service = LLMAnalysisService(client=mock_client)
    finding = _make_finding()
    finding.raw_data = {"source_code": "\n".join(f"line {i}" for i in range(1, 31))}

    session = AsyncMock()
    await service.analyze_finding(finding, session)

    prompt_arg = mock_client.analyze.call_args[0][0]
    assert "line" in prompt_arg


def test_extract_context_no_source():
    assert _extract_context(None, 5) == ""
    assert _extract_context("some code", None) == ""


def test_extract_context_returns_window():
    lines = [f"line{i}" for i in range(1, 51)]
    source = "\n".join(lines)
    context = _extract_context(source, 25)
    assert "line10" in context or "line25" in context
    assert len(context.splitlines()) <= 31


def test_extract_context_clamps_at_start():
    source = "a\nb\nc\nd\ne"
    context = _extract_context(source, 1)
    assert "1 |" in context

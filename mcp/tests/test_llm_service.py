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


# ---------------------------------------------------------------------------
# Tests: fetch_file_content integration in LLMAnalysisService (DATA-03)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_fetches_source_code_when_missing():
    mock_client = AsyncMock()
    mock_client.analyze.return_value = SAMPLE_OUTPUT

    mock_github = AsyncMock()
    mock_github.fetch_file_content.return_value = "line1\nline2\nline3"

    service = LLMAnalysisService(client=mock_client, github_client=mock_github)
    finding = _make_finding()
    finding.raw_data = {}  # no cached source

    session = AsyncMock()
    await service.analyze_finding(finding, session)

    mock_github.fetch_file_content.assert_called_once_with(finding.file_path)
    assert finding.raw_data.get("source_code") is not None


@pytest.mark.asyncio
async def test_analyze_skips_fetch_when_source_cached():
    mock_client = AsyncMock()
    mock_client.analyze.return_value = SAMPLE_OUTPUT

    mock_github = AsyncMock()

    service = LLMAnalysisService(client=mock_client, github_client=mock_github)
    finding = _make_finding()
    finding.raw_data = {"source_code": "def foo(): pass\n"}

    session = AsyncMock()
    await service.analyze_finding(finding, session)

    mock_github.fetch_file_content.assert_not_called()


@pytest.mark.asyncio
async def test_analyze_graceful_404():
    mock_client = AsyncMock()
    mock_client.analyze.return_value = SAMPLE_OUTPUT

    mock_github = AsyncMock()
    mock_github.fetch_file_content.return_value = None

    service = LLMAnalysisService(client=mock_client, github_client=mock_github)
    finding = _make_finding()
    finding.raw_data = {}

    session = AsyncMock()
    result = await service.analyze_finding(finding, session)

    assert result is not None  # no exception raised
    assert finding.raw_data.get("source_code") is None


@pytest.mark.asyncio
async def test_analyze_skips_fetch_for_binary_file():
    mock_client = AsyncMock()
    mock_client.analyze.return_value = SAMPLE_OUTPUT

    mock_github = AsyncMock()

    service = LLMAnalysisService(client=mock_client, github_client=mock_github)
    finding = _make_finding()
    finding.file_path = "build/libs/app.jar"
    finding.raw_data = {}

    session = AsyncMock()
    await service.analyze_finding(finding, session)

    mock_github.fetch_file_content.assert_not_called()


@pytest.mark.asyncio
async def test_analyze_skips_fetch_for_unknown_path():
    mock_client = AsyncMock()
    mock_client.analyze.return_value = SAMPLE_OUTPUT

    mock_github = AsyncMock()

    service = LLMAnalysisService(client=mock_client, github_client=mock_github)
    finding = _make_finding()
    finding.file_path = "unknown"
    finding.raw_data = {}

    session = AsyncMock()
    await service.analyze_finding(finding, session)

    mock_github.fetch_file_content.assert_not_called()

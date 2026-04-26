import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.llm.client import GeminiClient
from src.services.llm.schemas import AnalysisOutput

SAMPLE_OUTPUT = AnalysisOutput(
    vulnerability_id="CVE-2021-001",
    explanation_vi="Đây là lỗ hổng SQL Injection.",
    impact_vi="Kẻ tấn công có thể đọc toàn bộ dữ liệu.",
    remediation_diff="--- a/file.java\n+++ b/file.java\n@@ -1 +1 @@\n-vuln\n+safe",
    severity="HIGH",
    cwe_reference="CWE-89: SQL Injection",
    confidence="HIGH",
)


def _make_mock_client(output: AnalysisOutput) -> GeminiClient:
    client = GeminiClient.__new__(GeminiClient)
    client._max_retries = 3
    client._model = "gemini-2.5-flash"

    mock_inner = MagicMock()
    mock_inner.models.generate_content.return_value = MagicMock(
        text=output.model_dump_json()
    )
    client._client = mock_inner
    return client


@pytest.mark.asyncio
async def test_analyze_returns_analysis_output():
    client = _make_mock_client(SAMPLE_OUTPUT)
    result = await client.analyze("test prompt")
    assert isinstance(result, AnalysisOutput)
    assert result.severity == "HIGH"
    assert result.confidence == "HIGH"


@pytest.mark.asyncio
async def test_analyze_returns_vietnamese_fields():
    client = _make_mock_client(SAMPLE_OUTPUT)
    result = await client.analyze("test prompt")
    assert "lỗ hổng" in result.explanation_vi
    assert "tấn công" in result.impact_vi


@pytest.mark.asyncio
async def test_analyze_retries_on_rate_limit():
    client = GeminiClient.__new__(GeminiClient)
    client._max_retries = 3
    client._model = "gemini-2.5-flash"

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("429 RESOURCE_EXHAUSTED")
        return MagicMock(text=SAMPLE_OUTPUT.model_dump_json())

    mock_inner = MagicMock()
    mock_inner.models.generate_content.side_effect = side_effect
    client._client = mock_inner

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await client.analyze("test prompt")

    assert call_count == 3
    assert result.severity == "HIGH"


@pytest.mark.asyncio
async def test_analyze_raises_after_max_retries():
    client = GeminiClient.__new__(GeminiClient)
    client._max_retries = 2
    client._model = "gemini-2.5-flash"

    mock_inner = MagicMock()
    mock_inner.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED")
    client._client = mock_inner

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(RuntimeError, match="Gemini API"):
            await client.analyze("test prompt")


@pytest.mark.asyncio
async def test_analyze_raises_immediately_on_non_rate_limit_error():
    client = GeminiClient.__new__(GeminiClient)
    client._max_retries = 3
    client._model = "gemini-2.5-flash"

    mock_inner = MagicMock()
    mock_inner.models.generate_content.side_effect = Exception("Invalid API key")
    client._client = mock_inner

    with pytest.raises(Exception, match="Invalid API key"):
        await client.analyze("test prompt")

    assert mock_inner.models.generate_content.call_count == 1

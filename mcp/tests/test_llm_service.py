from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.schemas import AnalysisResult, FPInvestigation
from src.services.llm.schemas import (
    AnalysisOutput,
    CodeRef,
    FPInvestigationOutput,
    ReasoningStep,
)
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


# ---------------------------------------------------------------------------
# V4.3 — investigate_finding (data-flow FP investigation)
# ---------------------------------------------------------------------------

INV_SRC = (
    "def search(request):\n"
    "    q = request.GET['q']\n"
    "    cursor.execute('SELECT * FROM t WHERE id=' + q)\n"
    "    return q\n"
)


def _inv_finding(source=INV_SRC, tool="semgrep", rule_id="py.sqli"):
    f = _make_finding()
    f.tool = tool
    f.rule_id = rule_id
    f.line_number = 3
    f.raw_data = {"source_code": source} if source else {}
    return f


def _inv_output(verdict, quote, ls=3, le=3):
    return FPInvestigationOutput(
        verdict=verdict, confidence="HIGH", summary_vi="tóm tắt",
        reasoning_steps=[ReasoningStep(
            claim_vi="q từ request.GET tới sink cursor.execute",
            kind="sink", code_ref=CodeRef(file="f.py", line_start=ls, line_end=le), quote=quote,
        )],
        false_positive_likelihood="LOW",
    )


@pytest.mark.asyncio
async def test_investigate_true_positive_grounded():
    mock_client = AsyncMock()
    mock_client.investigate.return_value = _inv_output(
        "TRUE_POSITIVE", "cursor.execute('SELECT * FROM t WHERE id=' + q)")
    service = LLMAnalysisService(client=mock_client, github_client=AsyncMock())
    finding = _inv_finding()
    session = AsyncMock()

    result = await service.investigate_finding(finding, session)

    assert isinstance(result, FPInvestigation)
    assert result.verdict == "TRUE_POSITIVE"
    assert result.grounded is True
    assert result.steps[0].grounded is True
    assert result.suggested_command == "/fix 1"
    # advisory only — status untouched
    assert finding.status == "pending_review"


@pytest.mark.asyncio
async def test_investigate_false_positive_grounded_suggests_revoke():
    mock_client = AsyncMock()
    mock_client.investigate.return_value = _inv_output(
        "FALSE_POSITIVE", "q = request.GET['q']", ls=2, le=2)
    service = LLMAnalysisService(client=mock_client, github_client=AsyncMock())
    result = await service.investigate_finding(_inv_finding(), AsyncMock())

    assert result.verdict == "FALSE_POSITIVE"
    assert result.grounded is True
    assert result.suggested_command == "/revoke 1"


@pytest.mark.asyncio
async def test_investigate_fp_ungrounded_downgraded_to_uncertain():
    mock_client = AsyncMock()
    # quote references code NOT in the source -> ungrounded -> FP downgraded
    mock_client.investigate.return_value = _inv_output(
        "FALSE_POSITIVE", "sanitized = bleach.clean(q)  # not in source", ls=2, le=2)
    service = LLMAnalysisService(client=mock_client, github_client=AsyncMock())
    result = await service.investigate_finding(_inv_finding(), AsyncMock())

    assert result.verdict == "UNCERTAIN"
    assert result.confidence == "LOW"
    assert result.grounded is False
    assert result.suggested_command is None


@pytest.mark.asyncio
async def test_investigate_no_source_is_uncertain():
    mock_client = AsyncMock()
    mock_github = AsyncMock()
    mock_github.fetch_file_content.return_value = None
    service = LLMAnalysisService(client=mock_client, github_client=mock_github)
    finding = _inv_finding(source=None)

    result = await service.investigate_finding(finding, AsyncMock())

    assert result.verdict == "UNCERTAIN"
    assert result.source_available is False
    mock_client.investigate.assert_not_called()  # never LLM-decides FP from metadata


@pytest.mark.asyncio
async def test_investigate_dependency_short_circuits():
    mock_client = AsyncMock()
    service = LLMAnalysisService(client=mock_client, github_client=AsyncMock())
    finding = _inv_finding(tool="trivy", rule_id="CVE-2021-23337")

    result = await service.investigate_finding(finding, AsyncMock())

    assert result.verdict == "UNCERTAIN"
    assert result.source_available is False
    mock_client.investigate.assert_not_called()


@pytest.mark.asyncio
async def test_investigate_caches_result():
    mock_client = AsyncMock()
    mock_client.investigate.return_value = _inv_output(
        "TRUE_POSITIVE", "cursor.execute('SELECT * FROM t WHERE id=' + q)")
    service = LLMAnalysisService(client=mock_client, github_client=AsyncMock())
    finding = _inv_finding()
    session = AsyncMock()

    await service.investigate_finding(finding, session)
    await service.investigate_finding(finding, session)  # second call uses cache

    assert mock_client.investigate.call_count == 1


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


# ---------------------------------------------------------------------------
# V2.8 B4 — per-project Gemini key
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analyze_uses_project_gemini_key_when_set():
    """Project có gemini_api_key → tạo GeminiClient mới với key đó (cached)."""
    from src.services.llm import service as svc_mod

    captured: list[tuple[str, str]] = []

    class FakeGeminiClient:
        def __init__(self, api_key=None, model=None):
            captured.append((api_key, model))
            self.analyze = AsyncMock(return_value=SAMPLE_OUTPUT)

    project = MagicMock()
    project.github_token = "ghp_xxx"
    project.github_owner = "test"
    project.github_repo = "repo"
    project.gemini_api_key = "AIzaProject"
    project.gemini_model = "gemini-2.5-pro"

    artifact = MagicMock()
    artifact.project_id = 5

    session = AsyncMock()
    # session.get sequence: Artifact, Project
    session.get = AsyncMock(side_effect=[artifact, project])

    with patch.object(svc_mod, "GeminiClient", FakeGeminiClient), \
         patch.object(svc_mod, "GitHubClient") as mock_gh_cls:
        mock_gh = MagicMock()
        mock_gh.fetch_file_content = AsyncMock(return_value=None)
        mock_gh_cls.for_project = MagicMock(return_value=mock_gh)
        mock_gh_cls.return_value = mock_gh

        service = LLMAnalysisService()  # no injection → resolves from project
        finding = _make_finding()
        await service.analyze_finding(finding, session)

    assert captured == [("AIzaProject", "gemini-2.5-pro")]


@pytest.mark.asyncio
async def test_analyze_falls_back_to_env_when_project_has_no_key():
    """Project rỗng gemini_api_key → dùng settings (env)."""
    from src.core.config import settings
    from src.services.llm import service as svc_mod

    captured: list[tuple[str, str]] = []

    class FakeGeminiClient:
        def __init__(self, api_key=None, model=None):
            captured.append((api_key, model))
            self.analyze = AsyncMock(return_value=SAMPLE_OUTPUT)

    project = MagicMock()
    project.github_token = ""
    project.github_owner = ""
    project.github_repo = ""
    project.gemini_api_key = ""  # empty → fallback
    project.gemini_model = ""

    artifact = MagicMock()
    artifact.project_id = 6
    session = AsyncMock()
    session.get = AsyncMock(side_effect=[artifact, project])

    with patch.object(svc_mod, "GeminiClient", FakeGeminiClient), \
         patch.object(svc_mod, "GitHubClient") as mock_gh_cls:
        mock_gh = MagicMock()
        mock_gh.fetch_file_content = AsyncMock(return_value=None)
        mock_gh_cls.return_value = mock_gh

        service = LLMAnalysisService()
        finding = _make_finding()
        await service.analyze_finding(finding, session)

    assert captured == [(settings.GEMINI_API_KEY, settings.GEMINI_MODEL)]


@pytest.mark.asyncio
async def test_gemini_client_cached_per_key():
    """Cùng key gọi nhiều lần → tạo GeminiClient 1 lần (cache hit)."""
    from src.services.llm import service as svc_mod

    init_count = 0

    class FakeGeminiClient:
        def __init__(self, api_key=None, model=None):
            nonlocal init_count
            init_count += 1
            self.analyze = AsyncMock(return_value=SAMPLE_OUTPUT)

    project = MagicMock()
    project.github_token = ""
    project.gemini_api_key = "AIzaSame"
    project.gemini_model = "gemini-2.5-flash"
    project.github_owner = ""
    project.github_repo = ""

    artifact = MagicMock()
    artifact.project_id = 7

    with patch.object(svc_mod, "GeminiClient", FakeGeminiClient), \
         patch.object(svc_mod, "GitHubClient") as mock_gh_cls:
        mock_gh = MagicMock()
        mock_gh.fetch_file_content = AsyncMock(return_value=None)
        mock_gh_cls.return_value = mock_gh

        service = LLMAnalysisService()
        for _ in range(3):
            session = AsyncMock()
            session.get = AsyncMock(side_effect=[artifact, project])
            await service.analyze_finding(_make_finding(), session)

    assert init_count == 1  # cached after first instantiation

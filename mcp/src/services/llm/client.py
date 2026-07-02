from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from google import genai
from google.genai import types

from ...core.config import settings
from .prompt_loader import get_registry
from .schemas import AnalysisOutput

log = logging.getLogger(__name__)


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        """V2.8 B4 — per-project credentials.

        api_key / model rỗng → fallback settings (single-tenant default).
        Caller multi-tenant pass project-specific values để các project
        khác nhau dùng quota Gemini khác nhau (tránh đụng rate-limit).
        """
        effective_key = api_key or settings.GEMINI_API_KEY
        self._client = genai.Client(api_key=effective_key)
        self._model = model or settings.GEMINI_MODEL
        self._max_retries = settings.GEMINI_MAX_RETRIES

    async def analyze(self, prompt: str, system_prompt_id: str = "analyze") -> AnalysisOutput:
        # system_prompt_id chọn system instruction: "analyze" (SAST/code) hoặc
        # "cve" (dependency CVE — remediation là nâng cấp phiên bản).
        last_exc: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                response = await asyncio.to_thread(
                    self._client.models.generate_content,
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=AnalysisOutput,
                        system_instruction=get_registry().system_for(system_prompt_id),
                    ),
                )
                return AnalysisOutput.model_validate_json(response.text)
            except Exception as exc:
                last_exc = exc
                err_str = str(exc)
                if "429" in err_str or "503" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    wait = 2 ** attempt
                    log.warning("Gemini rate limit (attempt %d), retrying in %ds", attempt + 1, wait)
                    await asyncio.sleep(wait)
                else:
                    log.error("Gemini error (attempt %d): %s", attempt + 1, exc)
                    raise

        raise RuntimeError(f"Gemini API không phản hồi sau {self._max_retries} lần thử: {last_exc}")

    async def stream_analyze(
        self, prompt: str, system_prompt_id: str = "analyze",
    ) -> AsyncIterator[str]:
        """Stream the analysis text chunk-by-chunk for the SSE /explain endpoint.

        Yields text deltas as Gemini generates them (report §4.3.4, Mã A.10).
        Unlike `analyze()`, this does NOT enforce the AnalysisOutput JSON schema
        — it streams the free-form Vietnamese explanation so the frontend can
        render it progressively via EventSource. The structured POST /explain
        remains the canonical path for the machine-readable AnalysisResult.
        """
        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=get_registry().system_for(system_prompt_id),
                ),
            )
            async for chunk in stream:
                text = getattr(chunk, "text", None)
                if text:
                    yield text
        except Exception as exc:
            log.error("Gemini stream error: %s", exc)
            raise RuntimeError(f"Gemini streaming failed: {exc}")

    async def chat(self, prompt: str, context: str = "") -> str:
        """Free-form Vietnamese chat for the Shiftwall assistant.

        Returns plain text — no JSON schema enforced — so the assistant can
        answer general questions about security findings, the pipeline, or
        the project. `context` is concatenated to the user prompt and is
        intended to carry recent-finding summaries provided by the API layer.
        """
        full_prompt = (
            f"### Bối cảnh\n{context}\n\n### Câu hỏi của người dùng\n{prompt}"
            if context else prompt
        )
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = await asyncio.to_thread(
                    self._client.models.generate_content,
                    model=self._model,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=get_registry().system_for("chat"),
                        temperature=0.4,
                    ),
                )
                return (response.text or "").strip()
            except Exception as exc:
                last_exc = exc
                err_str = str(exc)
                if "429" in err_str or "503" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    await asyncio.sleep(2 ** attempt)
                    continue
                log.error("Gemini chat error: %s", exc)
                raise

        raise RuntimeError(f"Gemini chat không phản hồi: {last_exc}")

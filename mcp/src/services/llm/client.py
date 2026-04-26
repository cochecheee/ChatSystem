from __future__ import annotations

import asyncio
import logging

from google import genai
from google.genai import types

from ...core.config import settings
from .prompts import SYSTEM_INSTRUCTION
from .schemas import AnalysisOutput

log = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._model = settings.GEMINI_MODEL
        self._max_retries = settings.GEMINI_MAX_RETRIES

    async def analyze(self, prompt: str) -> AnalysisOutput:
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
                        system_instruction=SYSTEM_INSTRUCTION,
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

"""4-layer AI guardrail pipeline — see docs/guardrails.md.

Layer 1 (auth) lives in core/auth.py + main.py production-safety check.
Layer 2 (schema) is enforced at the FastAPI edge via Pydantic models.
This module owns:
  Layer 3 — ScrubbingService    (PII/secret removal before DB + LLM)
  Layer 4 — InjectionGuardrail  (prompt-injection check + sanitize)
"""
import os
import re
import tempfile

from detect_secrets import SecretsCollection

# ---------------------------------------------------------------------------
# Layer 3 — PII & Secret Scrubbing
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _looks_like_json(content: str) -> bool:
    """Cheap heuristic — JSON đúng spec phải bắt đầu với `{` hoặc `[`
    sau khi strip whitespace. Đủ chính xác cho SARIF/Trivy/DepCheck/ZAP
    output, không cần parse full để tránh tốn CPU trên file 700KB+."""
    stripped = content.lstrip()
    return stripped.startswith(("{", "["))


class ScrubbingService:
    """Removes secrets and PII from arbitrary text before passing to AI."""

    def scrub_content(self, content: str) -> str:
        """Scrub full text content (artifact pre-normalize OR source code).

        Skip toàn bộ scrub cho JSON content (SARIF, Trivy, DepCheck, ZAP) — V2.7.
        2 lý do silent breakage trên SARIF lớn (700KB+ codeql.sarif):
          1. detect-secrets `[SECRET_SCRUBBED]` thay full line → break `{}`
             bracket nếu flagged line là một entry JSON.
          2. Email regex ăn vào JSON escape: source code snippet trong SARIF
             có Python decorator như `\\n@app.route` — regex match `n@app.route`,
             ăn `n` của `\\n`, để lại `\\[EMAIL_SCRUBBED]` — `\\[` invalid JSON
             escape → entire SARIF không parse được → 0 finding ingest silent.

        Caller cần scrub PII trong field cụ thể (Finding.message etc.) dùng
        `scrub_text` post-parse — JSON skip ở đây không bỏ qua Layer 3 vì
        processor sẽ scrub_text từng field sau khi normalize.
        """
        if _looks_like_json(content):
            return content
        return self.scrub_text(content)

    def scrub_text(self, text: str) -> str:
        """Scrub plain text (Finding.message, source code fetched from GitHub).

        Áp dụng đầy đủ 3 pattern. An toàn vì input không phải JSON nên không
        có vấn đề break escape. Dùng sau khi parse SARIF/JSON outputs.
        """
        text = self._scrub_secrets(text)
        text = _EMAIL_RE.sub("[EMAIL_SCRUBBED]", text)
        text = _IPV4_RE.sub("[IP_SCRUBBED]", text)
        return text

    # ------------------------------------------------------------------

    def _scrub_secrets(self, content: str) -> str:
        """Replace lines containing detected secrets with [SECRET_SCRUBBED]."""
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".txt",
                delete=False,
                encoding="utf-8",
            ) as f:
                f.write(content)
                tmp_path = f.name

            collection = SecretsCollection()
            collection.scan_file(tmp_path)

            secret_line_numbers: set[int] = set()
            for _, secret_set in collection:
                for secret in secret_set:
                    secret_line_numbers.add(secret.line_number)

            if not secret_line_numbers:
                return content

            lines = content.split("\n")
            scrubbed = [
                "[SECRET_SCRUBBED]" if (i + 1) in secret_line_numbers else line
                for i, line in enumerate(lines)
            ]
            return "\n".join(scrubbed)

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Layer 4 — Prompt Injection Prevention
# ---------------------------------------------------------------------------

_MAX_CONTENT_LENGTH = 2000

_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"<script", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"forget\s+your\s+instructions?", re.IGNORECASE),
    re.compile(r"\bsystem\s+prompt\b", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
    re.compile(r"\bDAN\s+mode\b", re.IGNORECASE),
    re.compile(r"IGNORE\s+ALL", re.IGNORECASE),
    re.compile(r"\bSystem\.exit\b"),
    re.compile(r"you\s+are\s+now\b.{0,30}\bAI\b", re.IGNORECASE),
]


class InjectionGuardrail:
    """Detects and neutralises indirect prompt injection in SAST finding data."""

    def check(self, content: str) -> tuple[bool, str]:
        """Return (is_safe, reason). Unsafe content must not reach the LLM."""
        if len(content) > _MAX_CONTENT_LENGTH:
            return False, f"Content too long: {len(content)} chars (limit {_MAX_CONTENT_LENGTH})"

        for pattern in _INJECTION_PATTERNS:
            if pattern.search(content):
                return False, f"Injection pattern detected: {pattern.pattern!r}"

        return True, ""

    def sanitize(self, content: str) -> str:
        """Truncate and strip control characters for safe LLM input."""
        content = content[:_MAX_CONTENT_LENGTH]
        content = _CONTROL_CHARS_RE.sub("", content)
        return content

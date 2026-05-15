import pytest
from unittest.mock import MagicMock, patch

from src.core.guardrails import ScrubbingService


@pytest.fixture
def scrubber():
    return ScrubbingService()


# ---------------------------------------------------------------------------
# PII scrubbing
# ---------------------------------------------------------------------------

def test_scrubs_email(scrubber):
    result = scrubber.scrub_content("Contact admin@example.com for help")
    assert "admin@example.com" not in result
    assert "[EMAIL_SCRUBBED]" in result


def test_scrubs_ipv4(scrubber):
    result = scrubber.scrub_content("Connecting to 192.168.1.100 on port 8080")
    assert "192.168.1.100" not in result
    assert "[IP_SCRUBBED]" in result


def test_scrubs_multiple_pii(scrubber):
    content = "User user@test.com logged in from 10.0.0.1"
    result = scrubber.scrub_content(content)
    assert "[EMAIL_SCRUBBED]" in result
    assert "[IP_SCRUBBED]" in result


def test_no_pii_unchanged(scrubber):
    content = "SQL injection detected in src/db.py at line 42"
    result = scrubber.scrub_content(content)
    assert result == content


# ---------------------------------------------------------------------------
# Secret scrubbing (mocked detect-secrets)
# ---------------------------------------------------------------------------

def _make_mock_collection(secret_lines: set[int]):
    """Build a mock SecretsCollection that reports secrets on given line numbers."""
    mock_secret = MagicMock()
    mock_secret.line_number = next(iter(secret_lines)) if secret_lines else 0

    mock_secrets = [MagicMock(line_number=ln) for ln in secret_lines]

    mock_collection = MagicMock()
    mock_collection.__iter__ = MagicMock(
        return_value=iter([("file.txt", mock_secrets)])
    )
    mock_collection.scan_file = MagicMock()
    return mock_collection


def test_scrubs_secret_line(scrubber):
    content = "token=AKIAIOSFODNN7EXAMPLE\nnormal line"
    mock_collection = _make_mock_collection({1})

    with patch("src.core.guardrails.SecretsCollection", return_value=mock_collection):
        result = scrubber.scrub_content(content)

    assert "[SECRET_SCRUBBED]" in result
    assert "AKIAIOSFODNN7EXAMPLE" not in result
    assert "normal line" in result


def test_no_secrets_content_unchanged(scrubber):
    content = "Use of exec() detected in src/app.py"
    mock_collection = _make_mock_collection(set())

    with patch("src.core.guardrails.SecretsCollection", return_value=mock_collection):
        result = scrubber.scrub_content(content)

    assert result == content


def test_scrubs_multiple_secret_lines(scrubber):
    lines = ["safe line", "secret_key=abc123xyz", "another safe line", "password=hunter2"]
    content = "\n".join(lines)
    mock_collection = _make_mock_collection({2, 4})

    with patch("src.core.guardrails.SecretsCollection", return_value=mock_collection):
        result = scrubber.scrub_content(content)

    result_lines = result.split("\n")
    assert result_lines[0] == "safe line"
    assert result_lines[1] == "[SECRET_SCRUBBED]"
    assert result_lines[2] == "another safe line"
    assert result_lines[3] == "[SECRET_SCRUBBED]"


# ---------------------------------------------------------------------------
# JSON skip — báo cáo tiến độ V2.7 fix CodeQL SARIF silent drop
# ---------------------------------------------------------------------------

def test_json_content_skipped_to_preserve_validity(scrubber):
    """SARIF JSON với Python decorator `\\n@app.route` — email regex
    nếu chạy sẽ ăn `n` từ `\\n` JSON escape → `\\[EMAIL_SCRUBBED]` invalid
    JSON escape. Scrubber phải skip JSON content entirely."""
    import json
    sarif_like = {
        "runs": [{
            "tool": {"driver": {"name": "CodeQL"}},
            "results": [{
                "ruleId": "py/xss",
                "level": "warning",
                "message": {"text": "@app.route('/user')\nreturn flask.render_template(name)"},
            }],
        }],
    }
    content = json.dumps(sarif_like)
    result = scrubber.scrub_content(content)
    # Phải parse được — chứng minh không có invalid escape inserted
    assert json.loads(result) == sarif_like


def test_json_array_skipped(scrubber):
    """JSON array (ESLint format) cũng phải skip — same family of issues."""
    import json
    content = '[{"messages":[{"ruleId":"x","line":1}]}]'
    result = scrubber.scrub_content(content)
    assert json.loads(result) == json.loads(content)


def test_non_json_still_scrubbed(scrubber):
    """Plain text content vẫn scrub đầy đủ — regression cho fix V2.7."""
    content = "User john@example.com from 10.0.0.5 hit XSS"
    result = scrubber.scrub_content(content)
    assert "[EMAIL_SCRUBBED]" in result
    assert "[IP_SCRUBBED]" in result
